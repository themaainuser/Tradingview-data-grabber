/** Axis helpers: "nice" tick values and compact number / time formatting. */

export function niceTicks(min: number, max: number, target = 6): number[] {
	if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
	if (min === max) return [min];
	const rawStep = (max - min) / Math.max(1, target);
	const magnitude = 10 ** Math.floor(Math.log10(rawStep));
	const residual = rawStep / magnitude;
	const step = (residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10) * magnitude;
	const ticks: number[] = [];
	for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) {
		ticks.push(Number(v.toPrecision(12)));
	}
	return ticks;
}

/** Formats an axis value using as many decimals as the tick step needs, and no more. */
export function formatAxis(value: number, step: number): string {
	if (!Number.isFinite(value)) return '';
	const abs = Math.abs(value);
	if (abs >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
	if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
	const decimals = step >= 1 ? 0 : Math.min(8, Math.ceil(-Math.log10(step)));
	return value.toLocaleString('en-US', {
		minimumFractionDigits: decimals,
		maximumFractionDigits: decimals
	});
}

const pad = (n: number) => String(n).padStart(2, '0');

/** UTC labels: the backend emits epoch seconds, so the axis is timezone-independent. */
export function formatTime(seconds: number, withTime: boolean): string {
	if (!Number.isFinite(seconds)) return '';
	const d = new Date(seconds * 1000);
	const date = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
	return withTime ? `${date} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}` : date;
}

/** True when bars are sub-daily so labels need a time of day. */
export function isIntraday(time: Float64Array): boolean {
	if (time.length < 2) return false;
	const step = Math.min(
		...Array.from({ length: Math.min(50, time.length - 1) }, (_, i) => time[i + 1] - time[i])
	);
	return step < 86_400;
}
