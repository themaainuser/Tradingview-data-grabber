/** Shared look of text-like form controls (text-input in DESIGN.md): surface-1 fill, hairline edge, 10px radius. Inside a card the fill drops to canvas so the field reads as inset. */
export const fieldClass =
	'h-10 w-full min-w-0 rounded-md border border-hairline bg-surface-1 in-data-[slot=card]:bg-canvas px-[14px] text-[15px] leading-none text-ink outline-none transition-[border-color,box-shadow] duration-150 ease-out placeholder:text-ink-muted focus-visible:border-accent-blue disabled:pointer-events-none disabled:opacity-40 aria-invalid:border-gradient-coral';
