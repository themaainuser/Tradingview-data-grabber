import {
	barRange,
	int,
	multParam,
	num,
	perBar,
	periodParam,
	periodsPerYearParam,
	VALUE,
	windowParam
} from './helpers';
import {
	atrSma,
	atrWilder,
	clamp,
	div,
	ema,
	emaSpan,
	logChange,
	map,
	nanArray,
	pctChange,
	rateOfChange,
	rollingMax,
	rollingMean,
	rollingMin,
	rollingStd,
	rollingSum,
	rollingVariance,
	scale,
	sub,
	trueRange,
	zip
} from './math';
import type { Series } from './math';
import type { IndicatorDefinition } from './types';

const ln = (x: number) => (x > 0 ? Math.log(x) : NaN);

/** `sqrt(variance * periodsPerYear)` in percent; a negative variance estimate is undefined. */
const annualise = (variance: Series, periodsPerYear: number): Series =>
	map(variance, (v) => (v >= 0 ? Math.sqrt(v * periodsPerYear) * 100 : NaN));

const rangeEstimator = (
	id: string,
	name: string,
	short: string,
	description: string,
	perBarVariance: (o: number, h: number, l: number, c: number) => number
): IndicatorDefinition => ({
	id,
	name,
	short,
	description,
	category: 'Volatility',
	pane: 'separate',
	params: [windowParam(20), periodsPerYearParam()],
	outputs: VALUE,
	compute: (d, p) => [annualise(rollingMean(perBar(d, perBarVariance), p.window), p.periodsPerYear)]
});

export const volatilityIndicators: IndicatorDefinition[] = [
	{
		id: 'true_range',
		name: 'True Range',
		short: 'TR',
		description:
			'Largest of the bar range and the gaps from the previous close to the high and low.',
		category: 'Volatility',
		pane: 'separate',
		params: [],
		outputs: VALUE,
		compute: (d) => [trueRange(d.high, d.low, d.close)]
	},
	{
		id: 'atr',
		name: 'Average True Range (SMA)',
		short: 'ATR',
		description: 'Simple rolling mean of the true range (matches the backend atr_14).',
		category: 'Volatility',
		pane: 'separate',
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => [atrSma(d.high, d.low, d.close, p.period)]
	},
	{
		id: 'atr_wilder',
		name: 'Average True Range (Wilder)',
		short: 'ATR-W',
		description: 'Wilder-smoothed true range (alpha = 1 / N).',
		category: 'Volatility',
		pane: 'separate',
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => [atrWilder(d.high, d.low, d.close, p.period)]
	},
	{
		id: 'natr',
		name: 'Normalized ATR',
		short: 'NATR',
		description: 'Wilder ATR as a percent of the close, comparable across price levels.',
		category: 'Volatility',
		pane: 'separate',
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => [scale(div(atrWilder(d.high, d.low, d.close, p.period), d.close), 100)]
	},
	{
		id: 'stdev_returns',
		name: 'Rolling Std Dev of Returns',
		short: 'σ ret',
		description:
			'Sample standard deviation of one-bar simple returns over N bars, in percent (not annualised).',
		category: 'Volatility',
		pane: 'separate',
		params: [windowParam(20)],
		outputs: VALUE,
		compute: (d, p) => [rollingStd(scale(pctChange(d.close), 100), p.window, 1)]
	},
	{
		id: 'hist_vol',
		name: 'Historical Volatility',
		short: 'HV',
		description: 'Annualised sample standard deviation of one-bar log returns, in percent.',
		category: 'Volatility',
		pane: 'separate',
		params: [windowParam(20), periodsPerYearParam()],
		outputs: VALUE,
		compute: (d, p) => [
			scale(rollingStd(logChange(d.close), p.window, 1), 100 * Math.sqrt(p.periodsPerYear))
		]
	},
	rangeEstimator(
		'parkinson',
		'Parkinson Volatility',
		'Park',
		'Annualised range-based volatility estimator using only the high-low range, in percent.',
		(_o, h, l) => ln(h / l) ** 2 / (4 * Math.LN2)
	),
	rangeEstimator(
		'garman_klass',
		'Garman-Klass Volatility',
		'GK',
		'Annualised OHLC volatility estimator that combines the range and the open-close move, in percent.',
		(o, h, l, c) => 0.5 * ln(h / l) ** 2 - (2 * Math.LN2 - 1) * ln(c / o) ** 2
	),
	rangeEstimator(
		'rogers_satchell',
		'Rogers-Satchell Volatility',
		'RS',
		'Annualised OHLC volatility estimator that stays unbiased under drift, in percent.',
		(o, h, l, c) => ln(h / c) * ln(h / o) + ln(l / c) * ln(l / o)
	),
	{
		id: 'yang_zhang',
		name: 'Yang-Zhang Volatility',
		short: 'YZ',
		description:
			'Annualised estimator combining overnight gaps, open-close and Rogers-Satchell variance, in percent.',
		category: 'Volatility',
		pane: 'separate',
		params: [windowParam(20), periodsPerYearParam()],
		outputs: VALUE,
		compute: (d, p) => {
			const n = d.close.length;
			const overnight = nanArray(n);
			for (let i = 1; i < n; i++) overnight[i] = ln(d.open[i] / d.close[i - 1]);
			const intraday = perBar(d, (o, _h, _l, c) => ln(c / o));
			const rs = perBar(d, (o, h, l, c) => ln(h / c) * ln(h / o) + ln(l / c) * ln(l / o));
			const k = 0.34 / (1.34 + (p.window + 1) / (p.window - 1));
			const varOvernight = rollingVariance(overnight, p.window, 1);
			const varIntraday = rollingVariance(intraday, p.window, 1);
			const meanRs = rollingMean(rs, p.window);
			const variance = nanArray(n);
			for (let i = 0; i < n; i++) {
				variance[i] = varOvernight[i] + k * varIntraday[i] + (1 - k) * meanRs[i];
			}
			return [annualise(variance, p.periodsPerYear)];
		}
	},
	{
		id: 'ewma_vol',
		name: 'EWMA Volatility (RiskMetrics)',
		short: 'EWMA vol',
		description:
			'Annualised exponentially weighted volatility of log returns with decay lambda, in percent.',
		category: 'Volatility',
		pane: 'separate',
		params: [
			num('lambda', 'Decay (lambda)', 0.94, 0.5, 0.999, 0.005),
			int('warmup', 'Warm-up bars', 20, 2, 500),
			periodsPerYearParam()
		],
		outputs: VALUE,
		compute: (d, p) => {
			const squared = map(logChange(d.close), (r) => r * r);
			return [annualise(ema(squared, 1 - p.lambda, p.warmup), p.periodsPerYear)];
		}
	},
	{
		id: 'chaikin_volatility',
		name: 'Chaikin Volatility',
		short: 'CV',
		description: 'Percent change over K bars of an EMA of the high-low range.',
		category: 'Volatility',
		pane: 'separate',
		guides: [0],
		params: [periodParam(10), int('rocPeriod', 'ROC period', 10, 1, 200)],
		outputs: VALUE,
		compute: (d, p) => [rateOfChange(emaSpan(barRange(d), p.period), p.rocPeriod)]
	},
	{
		id: 'ulcer_index',
		name: 'Ulcer Index',
		short: 'UI',
		description:
			'Root-mean-square percent drawdown from the N-bar closing high; measures downside pain.',
		category: 'Volatility',
		pane: 'separate',
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => {
			const peak = rollingMax(d.close, p.period);
			const drawdown = zip(d.close, peak, (c, m) => (m > 0 ? (100 * (c - m)) / m : NaN));
			return [
				map(
					rollingMean(
						map(drawdown, (x) => x * x),
						p.period
					),
					Math.sqrt
				)
			];
		}
	},
	{
		id: 'donchian_width',
		name: 'Donchian Channel Width',
		short: 'DC width',
		description: 'N-bar high-low range as a percent of the channel midpoint.',
		category: 'Volatility',
		pane: 'separate',
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => {
			const hi = rollingMax(d.high, p.period);
			const lo = rollingMin(d.low, p.period);
			return [zip(hi, lo, (h, l) => (h + l === 0 ? NaN : (200 * (h - l)) / (h + l)))];
		}
	},
	{
		id: 'bollinger_bandwidth',
		name: 'Bollinger Bandwidth',
		short: 'BBW',
		description: 'Distance between the Bollinger Bands as a percent of the middle band.',
		category: 'Volatility',
		pane: 'separate',
		params: [periodParam(20), multParam(2)],
		outputs: VALUE,
		compute: (d, p) => [
			div(scale(rollingStd(d.close, p.period, 0), 200 * p.mult), rollingMean(d.close, p.period))
		]
	},
	{
		id: 'choppiness',
		name: 'Choppiness Index',
		short: 'CHOP',
		description:
			'Log ratio of summed true range to the N-bar range (0-100); high values mean a sideways market.',
		category: 'Volatility',
		pane: 'separate',
		guides: [38.2, 61.8],
		params: [periodParam(14, 2)],
		outputs: VALUE,
		compute: (d, p) => {
			const sumTr = rollingSum(trueRange(d.high, d.low, d.close), p.period);
			const range = sub(rollingMax(d.high, p.period), rollingMin(d.low, p.period));
			const ratio = zip(sumTr, range, (s, r) =>
				r > 0 && s > 0 ? Math.log10(s / r) / Math.log10(p.period) : NaN
			);
			return [clamp(scale(ratio, 100), 0, 100)];
		}
	},
	{
		id: 'range_atr',
		name: 'Range over ATR',
		short: 'Rng/ATR',
		description: 'Current bar high-low range divided by the Wilder ATR; flags unusually wide bars.',
		category: 'Volatility',
		pane: 'separate',
		guides: [1],
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => [div(barRange(d), atrWilder(d.high, d.low, d.close, p.period))]
	},
	{
		id: 'mass_index',
		name: 'Mass Index',
		short: 'MI',
		description:
			'Sum of the ratio between a single and a double EMA of the high-low range; spots range reversals.',
		category: 'Volatility',
		pane: 'separate',
		guides: [27],
		params: [int('emaPeriod', 'EMA span', 9, 1, 100), int('sumPeriod', 'Sum period', 25, 1, 200)],
		outputs: VALUE,
		compute: (d, p) => {
			const single = emaSpan(barRange(d), p.emaPeriod);
			const double = emaSpan(single, p.emaPeriod);
			return [rollingSum(div(single, double), p.sumPeriod)];
		}
	}
];
