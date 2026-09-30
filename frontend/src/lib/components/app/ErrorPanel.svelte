<script lang="ts">
	import CircleAlert from '@lucide/svelte/icons/circle-alert';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import * as Alert from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import type { ApiError } from '$lib/api/errors';

	interface Props {
		error: ApiError;
		title?: string;
		onretry?: () => void;
	}

	let { error, title = 'Something went wrong', onretry }: Props = $props();
</script>

<Alert.Root variant="destructive" role="alert">
	<CircleAlert aria-hidden="true" />
	<Alert.Title>{title}</Alert.Title>
	<Alert.Description>
		<p class="text-pretty">{error.message}</p>
		{#if onretry && error.retryable}
			<Button variant="translucent" size="sm" class="mt-2" onclick={onretry}>
				<RefreshCw aria-hidden="true" /> Retry
			</Button>
		{/if}
	</Alert.Description>
</Alert.Root>
