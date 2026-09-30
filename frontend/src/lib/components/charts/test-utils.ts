import type { Component, ComponentProps } from 'svelte';
import { render } from 'vitest-browser-svelte';

/** Mounts a chart in a host div of a known width (charts measure their container). */
export function mountChart<C extends Component<any>>( // eslint-disable-line @typescript-eslint/no-explicit-any
	component: C,
	props: NoInfer<ComponentProps<C>>,
	width = 600
) {
	const host = document.createElement('div');
	host.style.width = `${width}px`;
	document.body.append(host);
	const result = render(component as Component<Record<string, unknown>>, {
		props: props as Record<string, unknown>,
		target: host
	});
	return {
		host,
		result,
		resize: (next: number) => (host.style.width = `${next}px`)
	};
}

export const tooltipEl = () => document.querySelector<HTMLElement>('[data-slot="chart-tooltip"]');
export const tooltipText = () => tooltipEl()?.textContent ?? null;

export function pointer(type: string, target: Element, clientX: number, clientY: number) {
	target.dispatchEvent(
		new PointerEvent(type, { clientX, clientY, bubbles: true, pointerType: 'mouse' })
	);
}

/** Every colour an element paints with, from attributes and inline styles. */
export function paintOf(el: Element): string[] {
	const style = (el as SVGElement | HTMLElement).style;
	return [
		el.getAttribute('fill'),
		el.getAttribute('stroke'),
		el.getAttribute('style'),
		style?.fill,
		style?.stroke,
		style?.background
	].filter((v): v is string => !!v);
}

/** Parses `M x y L x y ...` path data into points. */
export function pathPoints(d: string | null): { x: number; y: number }[] {
	return [...(d ?? '').matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g)].map((m) => ({
		x: Number(m[1]),
		y: Number(m[2])
	}));
}
