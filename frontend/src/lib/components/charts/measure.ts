import type { Attachment } from 'svelte/attachments';

/**
 * Attachment reporting an element's width (rounded down, px) on mount and whenever it resizes.
 * Charts render at real pixel size, so they need the width rather than a scaled viewBox.
 */
export function measure(onWidth: (width: number) => void): Attachment<HTMLElement> {
	return (element) => {
		let last = -1;
		const report = (width: number) => {
			const next = Math.floor(width);
			if (next === last) return;
			last = next;
			onWidth(next);
		};
		report(element.clientWidth);
		const observer = new ResizeObserver((entries) => {
			report(entries[entries.length - 1].contentRect.width);
		});
		observer.observe(element);
		return () => observer.disconnect();
	};
}
