import type { ApiClient } from '$lib/api/client';
import type {
	ForwardResult,
	LedgerView,
	VerdictReport,
	VerdictRule,
	VerdictState
} from '$lib/api/contracts';
import { isAbort, toApiError, type ApiError } from '$lib/api/errors';
import {
	formFromDefaults,
	hasErrors,
	settingsDiffer,
	toRequest,
	validateForm,
	type FormErrors,
	type VerdictForm
} from '$lib/verdict/form';
import type { LoadStatus } from './datasets.svelte';

/** The backend allows one or two finalists to be frozen. */
export const MAX_FINALISTS = 2;

const EMPTY_FORM: VerdictForm = {
	minTrades: null,
	fee: null,
	spread: null,
	slippageK: null,
	periodsPerYear: null,
	holdoutFraction: 0.2
};

/**
 * The Verdict page: one dataset's seal, ledger, latest verdict, frozen rules and holdout read.
 *
 * The store holds only what the backend returned. Running, freezing and reading the holdout are
 * one-way actions: each is guarded against double submission, is never aborted mid-flight, and
 * after a failure the state is fetched again so the screen shows what the server actually did.
 */
export class VerdictStore {
	datasetId = $state<string | null>(null);
	status = $state<LoadStatus>('idle');
	error = $state.raw<ApiError | null>(null);
	state = $state.raw<VerdictState | null>(null);
	form = $state<VerdictForm>({ ...EMPTY_FORM });

	runStatus = $state<LoadStatus>('idle');
	runError = $state.raw<ApiError | null>(null);

	ledger = $state.raw<LedgerView | null>(null);
	ledgerStatus = $state<LoadStatus>('idle');
	ledgerError = $state.raw<ApiError | null>(null);

	selectedRuleIds = $state<string[]>([]);
	freezeStatus = $state<LoadStatus>('idle');
	freezeError = $state.raw<ApiError | null>(null);

	readStatus = $state<LoadStatus>('idle');
	readError = $state.raw<ApiError | null>(null);

	forward = $state.raw<ForwardResult | null>(null);
	forwardStatus = $state<LoadStatus>('idle');
	forwardError = $state.raw<ApiError | null>(null);

	readonly #api: ApiClient;
	#controller: AbortController | null = null;
	#formFor: string | null = null;

	constructor(api: ApiClient) {
		this.#api = api;
	}

	sealed = $derived(this.state?.sealed ?? false);
	report = $derived<VerdictReport | null>(this.state?.latest ?? null);
	errors = $derived<FormErrors>(validateForm(this.form, { sealed: this.sealed }));
	busy = $derived(
		this.runStatus === 'loading' || this.freezeStatus === 'loading' || this.readStatus === 'loading'
	);
	/** The ledger's hash chain is broken: the backend refuses every action that would change it. */
	locked = $derived(this.state ? !this.state.ledger.intact : false);
	canRun = $derived(!!this.state && !hasErrors(this.errors) && !this.busy && !this.locked);
	differs = $derived(this.report ? settingsDiffer(this.form, this.report) : false);

	candidates = $derived<VerdictRule[]>(
		this.report?.rules.filter((r) => r.evidence?.candidate) ?? []
	);

	canFreeze = $derived(
		this.report?.verdict.label === 'CANDIDATE' &&
			!!this.state &&
			!this.state.freeze &&
			this.selectedRuleIds.length >= 1 &&
			this.selectedRuleIds.length <= MAX_FINALISTS &&
			!this.busy &&
			!this.locked
	);

	canRead = $derived(
		!!this.state?.freeze &&
			this.state.holdout?.status === 'unread' &&
			!this.state.holdout_read &&
			!this.busy &&
			!this.locked
	);

	async open(id: string): Promise<void> {
		this.#controller?.abort();
		const controller = (this.#controller = new AbortController());
		const changed = this.datasetId !== id;
		this.datasetId = id;
		this.status = 'loading';
		this.error = null;
		if (changed) this.#resetDataset();
		try {
			const state = await this.#api.getVerdictState(id, { signal: controller.signal });
			if (controller !== this.#controller) return;
			this.state = state;
			// Edits survive a refresh; a different dataset starts from the backend defaults.
			if (this.#formFor !== id) {
				this.form = formFromDefaults(state.defaults);
				this.#formFor = id;
			}
			this.status = 'ready';
		} catch (error) {
			if (isAbort(error) || controller !== this.#controller) return;
			this.error = toApiError(error);
			this.status = 'error';
		}
	}

	reload(): Promise<void> {
		return this.datasetId ? this.open(this.datasetId) : Promise.resolve();
	}

	/** Refetches the server's state without a loading state; used to reconcile after an action. */
	async #sync(): Promise<void> {
		const id = this.datasetId;
		if (!id) return;
		try {
			const state = await this.#api.getVerdictState(id);
			if (this.datasetId === id) this.state = state;
		} catch {
			// The action's own error is already shown; the next load will retry.
		}
	}

	#resetDataset(): void {
		this.state = null;
		this.runStatus = 'idle';
		this.runError = null;
		this.ledger = null;
		this.ledgerStatus = 'idle';
		this.ledgerError = null;
		this.selectedRuleIds = [];
		this.freezeStatus = 'idle';
		this.freezeError = null;
		this.readStatus = 'idle';
		this.readError = null;
		this.forward = null;
		this.forwardStatus = 'idle';
		this.forwardError = null;
	}

	/** Seals the holdout first when the dataset has none, then runs the verdict. */
	async run(): Promise<void> {
		const id = this.datasetId;
		if (!id || !this.state || !this.canRun) return;
		this.runStatus = 'loading';
		this.runError = null;
		try {
			if (!this.state.sealed) await this.#api.sealHoldout(id, this.form.holdoutFraction);
			const report = await this.#api.runVerdict(toRequest(id, this.form));
			if (this.datasetId !== id) return;
			const holdout = {
				fraction: report.data.holdout.fraction,
				start: report.data.holdout.start,
				end: report.data.holdout.end,
				bars: report.data.holdout.bars,
				sealed_at: report.data.holdout.sealed_at,
				status: report.data.holdout.status,
				read_at: report.data.holdout.read_at
			};
			this.state = {
				...this.state,
				sealed: true,
				holdout,
				ledger: report.ledger,
				latest: report
			};
			this.selectedRuleIds = [];
			this.ledger = null;
			this.ledgerStatus = 'idle';
			this.runStatus = 'ready';
			await this.#sync();
		} catch (error) {
			if (this.datasetId !== id) return;
			this.runError = toApiError(error);
			this.runStatus = 'error';
			await this.#sync();
		}
	}

	async loadLedger(limit = 100): Promise<void> {
		const id = this.datasetId;
		if (!id) return;
		this.ledgerStatus = 'loading';
		this.ledgerError = null;
		try {
			const ledger = await this.#api.getVerdictLedger(id, { limit });
			if (this.datasetId !== id) return;
			this.ledger = ledger;
			this.ledgerStatus = 'ready';
		} catch (error) {
			if (isAbort(error) || this.datasetId !== id) return;
			this.ledgerError = toApiError(error);
			this.ledgerStatus = 'error';
		}
	}

	/** Adds or removes a candidate from the finalists; only candidates can be chosen, at most two. */
	toggleFinalist(ruleId: string): void {
		if (this.selectedRuleIds.includes(ruleId)) {
			this.selectedRuleIds = this.selectedRuleIds.filter((id) => id !== ruleId);
		} else if (
			this.candidates.some((r) => r.id === ruleId) &&
			this.selectedRuleIds.length < MAX_FINALISTS
		) {
			this.selectedRuleIds = [...this.selectedRuleIds, ruleId];
		}
	}

	async freeze(): Promise<void> {
		const id = this.datasetId;
		const run = this.report;
		if (!id || !run || !this.canFreeze) return;
		this.freezeStatus = 'loading';
		this.freezeError = null;
		try {
			await this.#api.freezeRules(id, { run_id: run.run_id, rule_ids: [...this.selectedRuleIds] });
			if (this.datasetId !== id) return;
			this.freezeStatus = 'ready';
			this.ledger = null;
			await this.#sync();
		} catch (error) {
			if (this.datasetId !== id) return;
			this.freezeError = toApiError(error);
			this.freezeStatus = 'error';
			await this.#sync();
		}
	}

	/** The one-way action. The caller must have the user's explicit confirmation. */
	async readHoldout(): Promise<void> {
		const id = this.datasetId;
		const freeze = this.state?.freeze;
		if (!id || !freeze || !this.canRead) return;
		this.readStatus = 'loading';
		this.readError = null;
		try {
			await this.#api.readHoldout(id, freeze.id);
			if (this.datasetId !== id) return;
			this.readStatus = 'ready';
		} catch (error) {
			if (this.datasetId !== id) return;
			this.readError = toApiError(error);
			this.readStatus = 'error';
		}
		// Success or not, ask the server: a timeout can hide a read that did happen.
		this.ledger = null;
		await this.#sync();
	}

	async loadForward(): Promise<void> {
		const id = this.datasetId;
		if (!id || !this.state?.freeze) return;
		this.forwardStatus = 'loading';
		this.forwardError = null;
		try {
			const forward = await this.#api.getForward(id);
			if (this.datasetId !== id) return;
			this.forward = forward;
			this.forwardStatus = 'ready';
		} catch (error) {
			if (isAbort(error) || this.datasetId !== id) return;
			this.forwardError = toApiError(error);
			this.forwardStatus = 'error';
		}
	}
}
