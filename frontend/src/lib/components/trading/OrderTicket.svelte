<script lang="ts">
	import { untrack } from 'svelte';
	import Plus from '@lucide/svelte/icons/plus';
	import X from '@lucide/svelte/icons/x';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Switch } from '$lib/components/ui/switch';
	import * as Alert from '$lib/components/ui/alert';
	import * as Select from '$lib/components/ui/select';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import {
		money,
		percent,
		quantity,
		signedMoney,
		signedPercent,
		tone,
		DASH
	} from '$lib/trading/format';
	import {
		CLASSES,
		CLASS_LABELS,
		INTENT_LABELS,
		KIND_NAMES,
		TIME_IN_FORCE,
		TIME_IN_FORCE_LABELS,
		TYPES,
		TYPE_LABELS,
		buildOrder,
		describeOrder,
		emptyLeg,
		estimate,
		kindOf,
		normalize,
		type Estimate,
		type Intent,
		type OrderClass,
		type OrderDraft,
		type OrderType,
		type TimeInForce
	} from '$lib/trading/order';
	import Field from './Field.svelte';
	import SymbolPicker from './SymbolPicker.svelte';

	let { store, draft = $bindable() }: { store: TradingStore; draft: OrderDraft } = $props();

	interface Review {
		order: Record<string, unknown>;
		text: string;
		clientOrderId: string;
	}

	let attempted = $state(false);
	let review = $state.raw<Review | null>(null);
	let liveWord = $state('');
	let outcome = $state.raw<{ ok: boolean; message: string; unknown: string | null } | null>(null);

	const kind = $derived(kindOf(draft.symbol));
	const built = $derived(buildOrder(draft));
	const errors = $derived(attempted ? built.errors : {});
	const quote = $derived(
		store.quote.data && store.quote.data.symbol === draft.symbol.trim().toUpperCase()
			? store.quote.data
			: null
	);
	// Follows the quote: one that arrives while the review is open improves the estimate.
	const reviewEstimate = $derived<Estimate>(
		review ? estimate(draft, quote) : { amount: null, basis: '' }
	);
	const power = $derived(store.account.data?.buying_power ?? null);
	const real = $derived(store.realMoney);
	const mode = $derived(real ? 'LIVE' : 'paper');

	/** Every edit goes through here, so the choices always stay what the asset offers. */
	function change(patch: Partial<OrderDraft>) {
		draft = normalize({ ...draft, ...patch });
		review = null;
		outcome = null;
	}

	// A quote for the symbol being typed, once it stops changing.
	$effect(() => {
		const symbol = draft.symbol.trim().toUpperCase();
		if (draft.multiLeg || !/^[A-Z0-9][A-Z0-9._/-]{0,31}$/.test(symbol)) return;
		const timer = setTimeout(() => untrack(() => void store.loadQuote(symbol)), 400);
		return () => clearTimeout(timer);
	});

	function startReview() {
		attempted = true;
		outcome = null;
		liveWord = '';
		if (!built.order) {
			review = null;
			return;
		}
		const clientOrderId = `tvdata-${crypto.randomUUID()}`;
		review = {
			order: { ...built.order, client_order_id: clientOrderId },
			text: describeOrder(built.order),
			clientOrderId
		};
	}

	async function submit() {
		if (!review || store.submitting || (real && liveWord.trim() !== 'LIVE')) return;
		const result = await store.placeOrder(review.order);
		outcome = { ok: result.ok, message: result.message, unknown: result.unknown };
		if (result.ok) {
			review = null;
			attempted = false;
			liveWord = '';
			draft = normalize({
				...draft,
				qty: '',
				notional: '',
				limitPrice: '',
				stopPrice: '',
				trail: '',
				takeProfit: '',
				stopLoss: '',
				stopLossLimit: ''
			});
		} else if (result.unknown !== 'unclear') {
			review = null; // refused, or known not to exist: back to editing (a new review gets a new ID)
		} // unclear: stay on this review, so trying again reuses the ID and a duplicate is refused instead of placed twice
	}

	const setLeg = (i: number, patch: Partial<OrderDraft['legs'][number]>) =>
		change({ legs: draft.legs.map((leg, j) => (j === i ? { ...leg, ...patch } : leg)) });
	const costs = $derived(
		review &&
			reviewEstimate.amount !== null &&
			draft.side === 'buy' &&
			power !== null &&
			reviewEstimate.amount > power
	);
	const priced = $derived(draft.type === 'limit' || draft.type === 'stop_limit');
	const stopped = $derived(draft.type === 'stop' || draft.type === 'stop_limit');
	const exits = $derived(!draft.multiLeg && draft.orderClass !== 'simple');
	const canExtend = $derived(
		!draft.multiLeg &&
			draft.type === 'limit' &&
			(draft.timeInForce === 'day' || draft.timeInForce === 'gtc')
	);
</script>

<SectionCard
	id="order-ticket"
	title="Order ticket"
	description={`An order placed here goes to your ${mode} account.`}
>
	<form
		class="grid min-w-0 gap-5"
		aria-label="Order ticket"
		novalidate
		onsubmit={(e) => {
			e.preventDefault();
			if (!review) startReview();
		}}
	>
		<fieldset class="grid min-w-0 gap-5" disabled={store.submitting}>
			<div class="flex flex-wrap items-center gap-3">
				<ToggleGroup.Root
					type="single"
					size="sm"
					value={draft.multiLeg ? 'multi' : 'single'}
					onValueChange={(v) =>
						v &&
						change(
							v === 'multi'
								? { multiLeg: true, type: 'limit' }
								: { multiLeg: false, type: 'market' }
						)}
					aria-label="Order shape"
				>
					<ToggleGroup.Item value="single">Single order</ToggleGroup.Item>
					<ToggleGroup.Item value="multi">Multi-leg option</ToggleGroup.Item>
				</ToggleGroup.Root>
				{#if !draft.multiLeg && draft.symbol.trim()}<span
						class="type-caption text-ink-muted"
						data-testid="asset-kind">{KIND_NAMES[kind]}</span
					>{/if}
			</div>

			{#if !draft.multiLeg}
				<Field id="ticket-symbol" label="Symbol" error={errors.symbol}>
					<SymbolPicker
						{store}
						id="ticket-symbol"
						value={draft.symbol}
						onchange={(symbol) => change({ symbol })}
					/>
				</Field>

				{#if quote}
					<dl
						class="grid grid-cols-2 gap-3 rounded-lg bg-canvas p-3 type-body-sm tabular-nums md:grid-cols-5"
						data-testid="quote"
					>
						<div>
							<dt class="type-caption text-ink-muted">Bid</dt>
							<dd>
								{money(quote.bid, true)}{#if quote.bid_size !== null}<span
										class="ml-1 text-ink-muted">× {quantity(quote.bid_size)}</span
									>{/if}
							</dd>
						</div>
						<div>
							<dt class="type-caption text-ink-muted">Ask</dt>
							<dd>
								{money(quote.ask, true)}{#if quote.ask_size !== null}<span
										class="ml-1 text-ink-muted">× {quantity(quote.ask_size)}</span
									>{/if}
							</dd>
						</div>
						<div>
							<dt class="type-caption text-ink-muted">Last</dt>
							<dd>{money(quote.last, true)}</dd>
						</div>
						<div>
							<dt class="type-caption text-ink-muted">Today</dt>
							<dd class={tone(quote.change)}>
								{signedMoney(quote.change)}
								{signedPercent(quote.change_percent)}
							</dd>
						</div>
						<div>
							<dt class="type-caption text-ink-muted">Spread</dt>
							<dd>{money(quote.spread, true)}</dd>
						</div>
						{#if quote.implied_volatility !== null}
							<div>
								<dt class="type-caption text-ink-muted">Implied volatility</dt>
								<dd>{percent((quote.implied_volatility ?? 0) * 100)}</dd>
							</div>
							<div>
								<dt class="type-caption text-ink-muted">Delta</dt>
								<dd>{quote.greeks?.delta ?? DASH}</dd>
							</div>
						{/if}
					</dl>
				{:else if store.quote.problem && draft.symbol.trim()}
					<p class="type-caption text-ink-muted" data-testid="quote-problem">
						No quote: {store.quote.problem}
					</p>
				{/if}

				<div class="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-3">
					<Field id="ticket-side" label="Side">
						<ToggleGroup.Root
							type="single"
							size="sm"
							value={draft.side}
							onValueChange={(v) => v && change({ side: v as 'buy' | 'sell' })}
							aria-label="Side"
							id="ticket-side"
						>
							<ToggleGroup.Item value="buy" class="data-[state=on]:text-success-ink"
								>Buy</ToggleGroup.Item
							>
							<ToggleGroup.Item value="sell" class="data-[state=on]:text-coral-ink"
								>Sell</ToggleGroup.Item
							>
						</ToggleGroup.Root>
					</Field>
					<Field id="ticket-type" label="Order type" error={errors.type}>
						<Select.Root
							type="single"
							value={draft.type}
							onValueChange={(v) => v && change({ type: v as OrderType })}
						>
							<Select.Trigger id="ticket-type" class="w-full"
								>{TYPE_LABELS[draft.type]}</Select.Trigger
							>
							<Select.Content>
								{#each TYPES[kind] as t (t)}<Select.Item value={t} label={TYPE_LABELS[t]}
										>{TYPE_LABELS[t]}</Select.Item
									>{/each}
							</Select.Content>
						</Select.Root>
					</Field>
					<Field id="ticket-tif" label="Time in force" error={errors.timeInForce}>
						<Select.Root
							type="single"
							value={draft.timeInForce}
							onValueChange={(v) => v && change({ timeInForce: v as TimeInForce })}
						>
							<Select.Trigger id="ticket-tif" class="w-full"
								>{TIME_IN_FORCE_LABELS[draft.timeInForce]}</Select.Trigger
							>
							<Select.Content>
								{#each TIME_IN_FORCE[kind] as t (t)}<Select.Item
										value={t}
										label={TIME_IN_FORCE_LABELS[t]}>{TIME_IN_FORCE_LABELS[t]}</Select.Item
									>{/each}
							</Select.Content>
						</Select.Root>
					</Field>
				</div>
			{:else}
				<div class="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-3">
					<Field id="ticket-type" label="Pricing">
						<Select.Root
							type="single"
							value={draft.type}
							onValueChange={(v) => v && change({ type: v as OrderType })}
						>
							<Select.Trigger id="ticket-type" class="w-full"
								>{draft.type === 'market' ? 'Market' : 'Limit (net price)'}</Select.Trigger
							>
							<Select.Content>
								<Select.Item value="limit" label="Limit (net price)">Limit (net price)</Select.Item>
								<Select.Item value="market" label="Market">Market</Select.Item>
							</Select.Content>
						</Select.Root>
					</Field>
					<Field id="ticket-tif" label="Time in force">
						<Select.Root
							type="single"
							value={draft.timeInForce}
							onValueChange={(v) => v && change({ timeInForce: v as TimeInForce })}
						>
							<Select.Trigger id="ticket-tif" class="w-full"
								>{TIME_IN_FORCE_LABELS[draft.timeInForce]}</Select.Trigger
							>
							<Select.Content>
								{#each ['day', 'gtc'] as t (t)}<Select.Item
										value={t}
										label={TIME_IN_FORCE_LABELS[t as TimeInForce]}
										>{TIME_IN_FORCE_LABELS[t as TimeInForce]}</Select.Item
									>{/each}
							</Select.Content>
						</Select.Root>
					</Field>
					<Field
						id="ticket-qty"
						label="Strategies"
						error={errors.qty}
						hint="How many of the whole strategy."
					>
						<Input
							id="ticket-qty"
							value={draft.qty}
							inputmode="numeric"
							oninput={(e) => change({ qty: e.currentTarget.value })}
							aria-invalid={errors.qty ? 'true' : undefined}
						/>
					</Field>
				</div>
				<div class="grid gap-3" data-testid="legs">
					<p class="type-caption text-ink-muted">Legs (two to four option contracts)</p>
					{#each draft.legs as leg, i (i)}
						<div
							class="grid grid-cols-[minmax(0,1fr)] items-end gap-3 md:grid-cols-[minmax(0,2fr)_8rem_5rem_minmax(0,1.4fr)_auto]"
							role="group"
							aria-label="Leg {i + 1}"
						>
							<Field id="leg-{i}-symbol" label="Contract {i + 1}"
								><Input
									id="leg-{i}-symbol"
									value={leg.symbol}
									placeholder="AAPL260116C00250000"
									autocomplete="off"
									spellcheck="false"
									class="font-mono uppercase"
									oninput={(e) => setLeg(i, { symbol: e.currentTarget.value })}
								/></Field
							>
							<Field id="leg-{i}-side" label="Side">
								<Select.Root
									type="single"
									value={leg.side}
									onValueChange={(v) => v && setLeg(i, { side: v as 'buy' | 'sell' })}
								>
									<Select.Trigger id="leg-{i}-side" class="w-full"
										>{leg.side === 'buy' ? 'Buy' : 'Sell'}</Select.Trigger
									>
									<Select.Content
										><Select.Item value="buy" label="Buy">Buy</Select.Item><Select.Item
											value="sell"
											label="Sell">Sell</Select.Item
										></Select.Content
									>
								</Select.Root>
							</Field>
							<Field id="leg-{i}-ratio" label="Ratio"
								><Input
									id="leg-{i}-ratio"
									value={leg.ratio}
									inputmode="numeric"
									oninput={(e) => setLeg(i, { ratio: e.currentTarget.value })}
								/></Field
							>
							<Field id="leg-{i}-intent" label="Intent">
								<Select.Root
									type="single"
									value={leg.intent || 'none'}
									onValueChange={(v) =>
										v && setLeg(i, { intent: v === 'none' ? '' : (v as Intent) })}
								>
									<Select.Trigger id="leg-{i}-intent" class="w-full"
										>{leg.intent ? INTENT_LABELS[leg.intent] : 'Not set'}</Select.Trigger
									>
									<Select.Content>
										<Select.Item value="none" label="Not set">Not set</Select.Item>
										{#each Object.entries(INTENT_LABELS) as [value, label] (value)}<Select.Item
												{value}
												{label}>{label}</Select.Item
											>{/each}
									</Select.Content>
								</Select.Root>
							</Field>
							<Button
								type="button"
								variant="ghost"
								size="icon-sm"
								aria-label="Remove leg {i + 1}"
								disabled={draft.legs.length <= 2}
								onclick={() => change({ legs: draft.legs.filter((_, j) => j !== i) })}
								><X aria-hidden="true" /></Button
							>
						</div>
					{/each}
					{#if errors.legs}<p
							class="type-caption text-coral-ink"
							role="alert"
							data-testid="field-error"
						>
							{errors.legs}
						</p>{/if}
					<Button
						type="button"
						variant="translucent"
						size="xs"
						class="w-fit"
						disabled={draft.legs.length >= 4}
						onclick={() => change({ legs: [...draft.legs, emptyLeg()] })}
						><Plus aria-hidden="true" /> Add a leg</Button
					>
				</div>
			{/if}

			<div class="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-3">
				{#if !draft.multiLeg}
					<Field
						id="ticket-size"
						label={draft.sizeBy === 'notional'
							? 'Dollar amount'
							: kind === 'us_option'
								? 'Contracts'
								: 'Quantity'}
						error={errors.qty ?? errors.notional}
						hint={draft.sizeBy === 'qty' && kind !== 'us_option'
							? 'Fractions are allowed with time in force Day.'
							: undefined}
					>
						<div class="flex gap-2">
							{#if kind !== 'us_option' && draft.type === 'market'}
								<ToggleGroup.Root
									type="single"
									size="sm"
									value={draft.sizeBy}
									onValueChange={(v) => v && change({ sizeBy: v as 'qty' | 'notional' })}
									aria-label="Size by"
								>
									<ToggleGroup.Item value="qty">Qty</ToggleGroup.Item>
									<ToggleGroup.Item value="notional">$</ToggleGroup.Item>
								</ToggleGroup.Root>
							{/if}
							<Input
								id="ticket-size"
								value={draft.sizeBy === 'notional' ? draft.notional : draft.qty}
								inputmode="decimal"
								oninput={(e) =>
									change(
										draft.sizeBy === 'notional'
											? { notional: e.currentTarget.value }
											: { qty: e.currentTarget.value }
									)}
								aria-invalid={errors.qty || errors.notional ? 'true' : undefined}
							/>
						</div>
					</Field>
				{/if}
				{#if priced || (draft.multiLeg && draft.type === 'limit')}
					<Field
						id="ticket-limit"
						label={draft.multiLeg ? 'Net price' : 'Limit price'}
						error={errors.limitPrice}
						hint={draft.multiLeg ? 'Positive for a debit, negative for a credit.' : undefined}
					>
						<Input
							id="ticket-limit"
							value={draft.limitPrice}
							inputmode="decimal"
							oninput={(e) => change({ limitPrice: e.currentTarget.value })}
							aria-invalid={errors.limitPrice ? 'true' : undefined}
						/>
					</Field>
				{/if}
				{#if stopped}
					<Field id="ticket-stop" label="Stop price" error={errors.stopPrice}>
						<Input
							id="ticket-stop"
							value={draft.stopPrice}
							inputmode="decimal"
							oninput={(e) => change({ stopPrice: e.currentTarget.value })}
							aria-invalid={errors.stopPrice ? 'true' : undefined}
						/>
					</Field>
				{/if}
				{#if draft.type === 'trailing_stop'}
					<Field
						id="ticket-trail"
						label={draft.trailBy === 'price' ? 'Trail amount ($)' : 'Trail (%)'}
						error={errors.trail}
					>
						<div class="flex gap-2">
							<ToggleGroup.Root
								type="single"
								size="sm"
								value={draft.trailBy}
								onValueChange={(v) => v && change({ trailBy: v as 'price' | 'percent' })}
								aria-label="Trail by"
							>
								<ToggleGroup.Item value="percent">%</ToggleGroup.Item>
								<ToggleGroup.Item value="price">$</ToggleGroup.Item>
							</ToggleGroup.Root>
							<Input
								id="ticket-trail"
								value={draft.trail}
								inputmode="decimal"
								oninput={(e) => change({ trail: e.currentTarget.value })}
								aria-invalid={errors.trail ? 'true' : undefined}
							/>
						</div>
					</Field>
				{/if}
			</div>

			{#if !draft.multiLeg}
				<div class="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-3">
					{#if CLASSES[kind].length > 1}
						<Field id="ticket-class" label="Order class">
							<Select.Root
								type="single"
								value={draft.orderClass}
								onValueChange={(v) => v && change({ orderClass: v as OrderClass })}
							>
								<Select.Trigger id="ticket-class" class="w-full"
									>{CLASS_LABELS[draft.orderClass]}</Select.Trigger
								>
								<Select.Content
									>{#each CLASSES[kind] as c (c)}<Select.Item value={c} label={CLASS_LABELS[c]}
											>{CLASS_LABELS[c]}</Select.Item
										>{/each}</Select.Content
								>
							</Select.Root>
						</Field>
					{/if}
					{#if kind === 'us_option'}
						<Field id="ticket-intent" label="Position intent" error={errors.intent}>
							<Select.Root
								type="single"
								value={draft.intent || 'none'}
								onValueChange={(v) => v && change({ intent: v === 'none' ? '' : (v as Intent) })}
							>
								<Select.Trigger id="ticket-intent" class="w-full"
									>{draft.intent ? INTENT_LABELS[draft.intent] : 'Not set'}</Select.Trigger
								>
								<Select.Content>
									<Select.Item value="none" label="Not set">Not set</Select.Item>
									{#each Object.entries(INTENT_LABELS) as [value, label] (value)}<Select.Item
											{value}
											{label}>{label}</Select.Item
										>{/each}
								</Select.Content>
							</Select.Root>
						</Field>
					{/if}
					{#if canExtend}
						<div class="flex items-center gap-3 self-end pb-2">
							<Switch
								id="ticket-extended"
								checked={draft.extendedHours}
								onCheckedChange={(v) => change({ extendedHours: v })}
							/>
							<label for="ticket-extended" class="type-caption text-ink"
								>Trade in extended hours</label
							>
						</div>
					{/if}
				</div>
				{#if exits}
					<div class="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-3" data-testid="exit-legs">
						<Field
							id="ticket-tp"
							label="Take profit at"
							error={errors.takeProfit}
							hint={draft.orderClass === 'oto'
								? 'Fill in this or the stop loss, not both.'
								: undefined}
							><Input
								id="ticket-tp"
								value={draft.takeProfit}
								inputmode="decimal"
								oninput={(e) => change({ takeProfit: e.currentTarget.value })}
								aria-invalid={errors.takeProfit ? 'true' : undefined}
							/></Field
						>
						<Field id="ticket-sl" label="Stop loss at" error={errors.stopLoss}
							><Input
								id="ticket-sl"
								value={draft.stopLoss}
								inputmode="decimal"
								oninput={(e) => change({ stopLoss: e.currentTarget.value })}
								aria-invalid={errors.stopLoss ? 'true' : undefined}
							/></Field
						>
						<Field id="ticket-sll" label="Stop-loss limit (optional)" error={errors.stopLossLimit}
							><Input
								id="ticket-sll"
								value={draft.stopLossLimit}
								inputmode="decimal"
								oninput={(e) => change({ stopLossLimit: e.currentTarget.value })}
								aria-invalid={errors.stopLossLimit ? 'true' : undefined}
							/></Field
						>
					</div>
				{/if}
			{/if}
		</fieldset>

		{#if outcome}
			<Alert.Root
				variant={outcome.ok ? 'default' : 'destructive'}
				role={outcome.ok ? 'status' : 'alert'}
				data-testid="order-outcome"
			>
				<Alert.Description>
					<p class="text-pretty">{outcome.message}</p>
					{#if outcome.unknown === 'unclear'}<p class="mt-1 text-pretty">
							Placing it again reuses the same order ID, so Alpaca refuses it if the first one went
							through.
						</p>{/if}
				</Alert.Description>
			</Alert.Root>
		{/if}

		{#if review}
			<div
				class="grid gap-3 rounded-lg bg-canvas p-4 {real ? 'ring-1 ring-coral-ink' : ''}"
				role="group"
				aria-label="Review the order"
				data-testid="order-review"
			>
				<p class="type-caption text-ink-muted">
					Review: this goes to your <strong class={real ? 'text-coral-ink' : 'text-success-ink'}
						>{mode}</strong
					> account
				</p>
				<p class="type-body font-medium text-pretty" data-testid="review-text">{review.text}</p>
				<p class="type-body-sm text-ink-muted tabular-nums" data-testid="review-estimate">
					{#if reviewEstimate.amount !== null}Estimated {draft.side === 'buy'
							? 'cost'
							: 'proceeds'}: <span class="text-ink">{money(reviewEstimate.amount)}</span> · {reviewEstimate.basis}{:else}{reviewEstimate.basis}{/if}
					{#if power !== null}
						· Buying power {money(power)}{/if}
				</p>
				{#if costs}<p class="flex items-center gap-2 type-body-sm text-coral-ink" role="alert">
						<TriangleAlert class="size-4" aria-hidden="true" /> This is more than your buying power; Alpaca
						will probably refuse it.
					</p>{/if}
				{#if real}
					<label class="grid gap-1 type-caption text-ink-muted">
						<span
							>This uses real money. Type <strong class="text-coral-ink">LIVE</strong> to place it.</span
						>
						<Input
							bind:value={liveWord}
							autocomplete="off"
							spellcheck="false"
							aria-label="Type LIVE to confirm"
							class="w-40"
							data-testid="live-confirm"
						/>
					</label>
				{/if}
				<div class="flex flex-wrap gap-2">
					<Button
						type="button"
						variant={real ? 'destructive' : 'default'}
						disabled={store.submitting || (real && liveWord.trim() !== 'LIVE')}
						onclick={submit}
						data-testid="place-order"
					>
						{store.submitting ? 'Sending…' : real ? 'Place LIVE order' : 'Place paper order'}
					</Button>
					<Button
						type="button"
						variant="ghost"
						disabled={store.submitting}
						onclick={() => ((review = null), (outcome = null))}>Edit</Button
					>
				</div>
			</div>
		{:else}
			<div class="flex flex-wrap items-center gap-3">
				<Button
					type="submit"
					data-testid="review-order"
					disabled={store.submitting || !store.usable}>Review order</Button
				>
				{#if attempted && !built.order}<span class="type-caption text-coral-ink" role="alert"
						>Fix the highlighted fields first.</span
					>{/if}
			</div>
		{/if}
	</form>
</SectionCard>
