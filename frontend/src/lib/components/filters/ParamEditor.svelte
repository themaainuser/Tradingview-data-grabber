<script lang="ts">
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import * as Popover from '$lib/components/ui/popover';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import type { ParamSpec } from '$lib/indicators/types';

	interface Props {
		specs: readonly ParamSpec[];
		/** Fully resolved current values keyed by param key. */
		values: Readonly<Record<string, number>>;
		onchange: (values: Record<string, number>) => void;
		title?: string;
	}

	let { specs, values, onchange, title = 'Parameters' }: Props = $props();

	function update(key: string, event: Event & { currentTarget: HTMLInputElement }) {
		const value = event.currentTarget.valueAsNumber;
		// Ignore transient empty/invalid input; the registry clamps whatever remains.
		if (!Number.isFinite(value)) return;
		onchange({ ...values, [key]: value });
	}
</script>

<Popover.Root>
	<Popover.Trigger>
		{#snippet child({ props })}
			<Button {...props} variant="ghost" size="icon-sm" aria-label="{title}: edit parameters">
				<SlidersHorizontal aria-hidden="true" />
			</Button>
		{/snippet}
	</Popover.Trigger>
	<Popover.Content class="w-64" align="start">
		<p class="type-body-sm">{title}</p>
		<div class="grid gap-3">
			{#each specs as spec (spec.key)}
				<div class="grid gap-1.5">
					<Label for="param-{spec.key}" class="type-caption">{spec.label}</Label>
					<Input
						id="param-{spec.key}"
						type="number"
						class="tabular-nums"
						min={spec.min}
						max={spec.max}
						step={spec.step}
						value={values[spec.key]}
						oninput={(e) => update(spec.key, e)}
					/>
					<span class="type-caption text-ink-muted tabular-nums">{spec.min} – {spec.max}</span>
				</div>
			{/each}
		</div>
	</Popover.Content>
</Popover.Root>
