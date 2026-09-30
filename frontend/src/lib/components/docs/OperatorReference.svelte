<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { OPERATORS } from '$lib/filters/operators';
	import { groupBy } from '$lib/group';
	import type { OperatorFamily } from '$lib/filters/types';

	// Generated from the operator registry the filter engine itself uses, so this page cannot drift.
	const FAMILIES: Record<OperatorFamily, string> = {
		compare: 'Compare a value',
		series: 'Time series',
		distribution: 'Whole-sample distribution',
		validity: 'Validity',
		text: 'Text'
	};

	const groups = groupBy(OPERATORS, (o) => o.family);
</script>

<div class="grid gap-[30px]">
	{#each groups as [family, operators] (family)}
		<div class="grid gap-3">
			<h3 class="type-headline">{FAMILIES[family as OperatorFamily]}</h3>
			<div class="overflow-x-auto rounded-lg bg-canvas">
				<table class="w-full min-w-[34rem] text-left type-body-sm">
					<caption class="sr-only">{FAMILIES[family as OperatorFamily]} operators</caption>
					<thead class="type-caption text-ink-muted">
						<tr class="border-b border-hairline">
							<th scope="col" class="w-56 px-3 py-3 font-medium">Operator</th>
							<th scope="col" class="px-3 py-3 font-medium">What it matches</th>
						</tr>
					</thead>
					<tbody>
						{#each operators as op (op.id)}
							<tr class="border-b border-hairline-soft last:border-0" data-testid="operator-row">
								<th scope="row" class="px-3 py-3 align-top font-medium whitespace-nowrap">
									{op.label}
									<code class="ml-1 font-mono type-micro text-ink-muted">{op.id}</code>
								</th>
								<td class="px-3 py-3 align-top text-ink-muted">
									{op.description}
									<span class="mt-1.5 flex flex-wrap gap-1.5">
										{#if op.ordered}<Badge variant="secondary">Needs time-ordered data</Badge>{/if}
										{#if op.lookahead}<Badge variant="destructive">Uses the whole sample</Badge
											>{/if}
										{#if op.allowsField}<Badge variant="secondary"
												>Can compare with another field</Badge
											>{/if}
									</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	{/each}
</div>
