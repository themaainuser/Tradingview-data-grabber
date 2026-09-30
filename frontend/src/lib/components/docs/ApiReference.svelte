<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { API_ENDPOINTS } from '$lib/docs/api-reference';
</script>

<div class="grid gap-5">
	{#each API_ENDPOINTS as e (e.id)}
		<article
			class="grid gap-3 rounded-xl bg-surface-1 p-5"
			aria-labelledby="endpoint-{e.id}"
			data-testid="endpoint"
		>
			<header class="flex flex-wrap items-center gap-x-3 gap-y-1">
				<Badge variant={e.method === 'GET' ? 'success' : 'default'}>{e.method}</Badge>
				<h3 id="endpoint-{e.id}" class="font-mono type-body-sm">{e.path}</h3>
				<span class="ml-auto type-caption text-ink-muted">
					{e.usedBy ? `Used by ${e.usedBy}` : 'Available, not used by the UI yet'}
				</span>
			</header>
			<p class="type-body text-pretty text-ink-muted">{e.summary}</p>

			{#if e.params.length}
				<div class="overflow-x-auto rounded-lg bg-canvas">
					<table class="w-full min-w-[32rem] text-left type-caption">
						<caption class="sr-only">Parameters of {e.path}</caption>
						<thead class="text-ink-muted">
							<tr class="border-b border-hairline">
								<th scope="col" class="px-3 py-2 font-medium">Name</th>
								<th scope="col" class="px-3 py-2 font-medium">In</th>
								<th scope="col" class="px-3 py-2 font-medium">Type</th>
								<th scope="col" class="px-3 py-2 font-medium">Description</th>
							</tr>
						</thead>
						<tbody>
							{#each e.params as p (p.name)}
								<tr class="border-b border-hairline-soft last:border-0">
									<th
										scope="row"
										class="px-3 py-2 align-top font-mono font-medium whitespace-nowrap"
									>
										{p.name}{#if p.required}<span class="text-gradient-coral" title="required">
												*</span
											>{/if}
									</th>
									<td class="px-3 py-2 align-top text-ink-muted">{p.in}</td>
									<td class="px-3 py-2 align-top whitespace-nowrap text-ink-muted">{p.type}</td>
									<td class="px-3 py-2 align-top text-ink-muted">{p.description}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}

			<dl class="grid gap-2 type-caption">
				<div class="grid gap-1 sm:grid-cols-[6rem_minmax(0,1fr)]">
					<dt class="text-ink-muted">Returns</dt>
					<dd><code class="font-mono break-words">{e.returns}</code></dd>
				</div>
				{#if e.errors.length}
					<div class="grid gap-1 sm:grid-cols-[6rem_minmax(0,1fr)]">
						<dt class="text-ink-muted">Errors</dt>
						<dd class="grid gap-1">
							{#each e.errors as err (err.status)}
								<span><code class="font-mono">{err.status}</code> {err.when}</span>
							{/each}
						</dd>
					</div>
				{/if}
			</dl>
		</article>
	{/each}
</div>
