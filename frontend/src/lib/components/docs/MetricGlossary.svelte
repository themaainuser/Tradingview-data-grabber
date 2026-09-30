<script lang="ts">
	import { derivedColumns, METRICS, WINDOW_LABELS } from '$lib/research/columns';

	// Generated from the same definitions that build the results table's columns.
	const derived = derivedColumns();
	const windows = Object.values(WINDOW_LABELS);
</script>

<div class="grid gap-5">
	<div class="grid gap-3">
		<h3 class="type-headline">Per-window statistics</h3>
		<p class="type-body text-ink-muted">
			Every statistic below is reported for each of the {windows.length} windows ({windows.join(
				', '
			)}), giving
			{METRICS.length * windows.length} columns per strategy.
		</p>
		<div class="overflow-x-auto rounded-lg bg-canvas">
			<table class="w-full min-w-[32rem] text-left type-body-sm">
				<caption class="sr-only">Per-window statistics</caption>
				<thead class="type-caption text-ink-muted">
					<tr class="border-b border-hairline">
						<th scope="col" class="w-44 px-3 py-3 font-medium">Statistic</th>
						<th scope="col" class="px-3 py-3 font-medium">Meaning</th>
					</tr>
				</thead>
				<tbody>
					{#each METRICS as m (m.key)}
						<tr class="border-b border-hairline-soft last:border-0" data-testid="metric-row">
							<th scope="row" class="px-3 py-3 align-top font-medium">{m.label}</th>
							<td class="px-3 py-3 align-top text-ink-muted">{m.description}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>

	<div class="grid gap-3">
		<h3 class="type-headline">Derived columns</h3>
		<div class="overflow-x-auto rounded-lg bg-canvas">
			<table class="w-full min-w-[32rem] text-left type-body-sm">
				<caption class="sr-only">Derived columns</caption>
				<thead class="type-caption text-ink-muted">
					<tr class="border-b border-hairline">
						<th scope="col" class="w-44 px-3 py-3 font-medium">Column</th>
						<th scope="col" class="px-3 py-3 font-medium">Meaning</th>
					</tr>
				</thead>
				<tbody>
					{#each derived as c (c.key)}
						<tr class="border-b border-hairline-soft last:border-0" data-testid="derived-row">
							<th scope="row" class="px-3 py-3 align-top font-medium">
								{c.label}
								<span class="block type-micro text-ink-muted">{c.group}</span>
							</th>
							<td class="px-3 py-3 align-top text-ink-muted">{c.description}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
</div>
