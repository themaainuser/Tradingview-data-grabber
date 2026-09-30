<script lang="ts">
	import type { Attachment } from 'svelte/attachments';
	import {
		LineChartController,
		type LineHover,
		type LineSeries
	} from '$lib/charts/line-controller';
	import { formatTime } from '$lib/charts/scale';
	import { formatValue } from '$lib/format';

	interface Props {
		series: readonly LineSeries[];
		label: string;
	}

	let { series, label }: Props = $props();
	let hover = $state.raw<LineHover | null>(null);

	const chart: Attachment<HTMLCanvasElement> = (canvas) => {
		const controller = new LineChartController(canvas, (h) => (hover = h));
		$effect(() => {
			controller.set(series);
		});
		return () => controller.destroy();
	};

	const values = $derived(new Map((hover?.values ?? []).map((v) => [v.key, v.value])));
</script>

<figure class="grid gap-2">
	<figcaption class="flex flex-wrap items-center gap-x-4 gap-y-1 type-caption tabular-nums">
		<span class="min-w-32 text-ink-muted"
			>{hover ? formatTime(hover.time, false) : 'Hover for values'}</span
		>
		{#each series as s (s.key)}
			<span class="inline-flex items-center gap-1.5">
				<span
					class="inline-block h-0.5 w-3 rounded-full"
					style:background={s.dashed ? 'transparent' : `var(${s.color})`}
					style:border-top={s.dashed ? `2px dashed var(${s.color})` : undefined}
					aria-hidden="true"
				></span>
				<span class="text-ink-muted">{s.label}</span>
				{#if hover}{formatValue(values.get(s.key), 'ratio')}{/if}
			</span>
		{/each}
	</figcaption>
	<div role="img" aria-label={label}>
		<canvas {@attach chart} class="h-72 w-full rounded-lg" aria-hidden="true"></canvas>
	</div>
</figure>
