/**
 * Shared canvas plumbing: device-pixel-ratio sizing, coalesced redraws and theme-aware colours.
 *
 * Redraws are requested with `schedule()` and batched into one animation frame, so a burst of
 * pointer moves or reactive updates paints at most once per frame.
 */
export interface CanvasHost {
	readonly ctx: CanvasRenderingContext2D;
	/** CSS pixel size of the drawing surface. */
	readonly width: number;
	readonly height: number;
	schedule(): void;
	/** Resolves a `--custom-property` name (or passes a literal colour through) for this frame. */
	color(value: string): string;
	destroy(): void;
}

export function createCanvasHost(
	canvas: HTMLCanvasElement,
	draw: (host: CanvasHost) => void
): CanvasHost {
	const ctx = canvas.getContext('2d');
	if (!ctx) throw new Error('Canvas 2D is not available in this browser');
	let width = 0;
	let height = 0;
	let frame = 0;
	let colors = new Map<string, string>();

	const host: CanvasHost = {
		ctx,
		get width() {
			return width;
		},
		get height() {
			return height;
		},
		schedule() {
			if (frame) return;
			frame = requestAnimationFrame(() => {
				frame = 0;
				colors = new Map();
				if (width > 0 && height > 0) draw(host);
			});
		},
		color(value) {
			if (!value.startsWith('--')) return value;
			let resolved = colors.get(value);
			if (resolved === undefined) {
				resolved = getComputedStyle(canvas).getPropertyValue(value).trim() || 'currentColor';
				colors.set(value, resolved);
			}
			return resolved;
		},
		destroy() {
			cancelAnimationFrame(frame);
			resizeObserver.disconnect();
			themeObserver.disconnect();
		}
	};

	const resize = () => {
		const ratio = window.devicePixelRatio || 1;
		const rect = canvas.getBoundingClientRect();
		width = Math.max(0, Math.floor(rect.width));
		height = Math.max(0, Math.floor(rect.height));
		canvas.width = Math.floor(width * ratio);
		canvas.height = Math.floor(height * ratio);
		ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
		host.schedule();
	};
	const resizeObserver = new ResizeObserver(resize);
	resizeObserver.observe(canvas);
	// The theme is `data-theme` on <html>; repaint when it flips so token colours are re-resolved
	// (schedule() drops the per-frame colour cache).
	const themeObserver = new MutationObserver(() => host.schedule());
	themeObserver.observe(document.documentElement, {
		attributes: true,
		attributeFilter: ['data-theme']
	});
	resize();
	return host;
}
