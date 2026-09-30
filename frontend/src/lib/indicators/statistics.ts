import { int, periodsPerYearParam, VALUE, windowParam } from './helpers';
import {
	clamp,
	finiteRun,
	logChange,
	map,
	nanArray,
	pctChange,
	pctDiff,
	rateOfChange,
	rollingAutocorrelation,
	rollingKurtosis,
	rollingMax,
	rollingMean,
	rollingMin,
	rollingPercentRank,
	rollingSkew,
	rollingStd,
	scale,
	zScore,
	zip
} from './math';
import type { Series } from './math';
import type { IndicatorDefinition } from './types';

/** Percent drawdown from the running maximum of all finite closes so far. */
function drawdownFromPeak(close: Series): Series {
	const out = nanArray(close.length);
	let peak = -Infinity;
	for (let i = 0; i < close.length; i++) {
		const c = close[i];
		if (!Number.isFinite(c)) continue;
		if (c > peak) peak = c;
		out[i] = peak > 0 ? 100 * (c / peak - 1) : NaN;
	}
	return out;
}

/** Worst percent drawdown inside each window, measured from the running peak within that window. */
function rollingMaxDrawdown(close: Series, w: number): Series {
	const n = close.length;
	const out = nanArray(n);
	const run = finiteRun(close);
	for (let i = w - 1; i < n; i++) {
		if (run[i] < w) continue;
		let peak = -Infinity;
		let worst = 0;
		for (let j = i - w + 1; j <= i; j++) {
			if (close[j] > peak) peak = close[j];
			const dd = close[j] / peak - 1;
			if (dd < worst) worst = dd;
		}
		out[i] = peak > 0 ? 100 * worst : NaN;
	}
	return out;
}

const returnsPercent = (close: Series): Series => scale(pctChange(close), 100);

export const statisticsIndicators: IndicatorDefinition[] = [
	{
		id: 'simple_return',
		name: 'Simple Return',
		short: 'Ret',
		description: 'One-bar percent change of the close.',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [],
		outputs: VALUE,
		compute: (d) => [returnsPercent(d.close)]
	},
	{
		id: 'log_return',
		name: 'Log Return',
		short: 'LogRet',
		description: 'One-bar natural-log return of the close, in percent.',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [],
		outputs: VALUE,
		compute: (d) => [scale(logChange(d.close), 100)]
	},
	{
		id: 'rolling_return',
		name: 'Rolling Return',
		short: 'RollRet',
		description: 'Percent change of the close over the last N bars.',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [int('period', 'Period', 20, 1, 1000)],
		outputs: VALUE,
		compute: (d, p) => [rateOfChange(d.close, p.period)]
	},
	{
		id: 'mean_return',
		name: 'Rolling Mean Return',
		short: 'μ ret',
		description: 'Average one-bar percent return over the last N bars.',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [windowParam(20)],
		outputs: VALUE,
		compute: (d, p) => [rollingMean(returnsPercent(d.close), p.window)]
	},
	{
		id: 'zscore',
		name: 'Rolling Z-Score of Close',
		short: 'Z',
		description:
			'Standard score of the close against its N-bar mean and sample standard deviation.',
		category: 'Statistics',
		pane: 'separate',
		guides: [-2, 0, 2],
		params: [windowParam(20)],
		outputs: VALUE,
		compute: (d, p) => [
			zScore(d.close, rollingMean(d.close, p.window), rollingStd(d.close, p.window, 1))
		]
	},
	{
		id: 'percent_rank',
		name: 'Rolling Percent Rank',
		short: 'PctRank',
		description: 'Percent of the previous N closes that are below the current close (0-100).',
		category: 'Statistics',
		pane: 'separate',
		guides: [20, 50, 80],
		params: [windowParam(100, 2, 250)],
		outputs: VALUE,
		compute: (d, p) => [rollingPercentRank(d.close, p.window)]
	},
	{
		id: 'skew',
		name: 'Rolling Skewness of Returns',
		short: 'Skew',
		description:
			'Bias-corrected sample skewness of one-bar returns over N bars; negative means a fat left tail.',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [windowParam(60, 4, 500)],
		outputs: VALUE,
		compute: (d, p) => [rollingSkew(pctChange(d.close), p.window)]
	},
	{
		id: 'kurtosis',
		name: 'Rolling Excess Kurtosis of Returns',
		short: 'Kurt',
		description:
			'Bias-corrected excess kurtosis of one-bar returns over N bars; positive means fat tails.',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [windowParam(60, 5, 500)],
		outputs: VALUE,
		compute: (d, p) => [rollingKurtosis(pctChange(d.close), p.window)]
	},
	{
		id: 'sharpe',
		name: 'Rolling Sharpe Ratio',
		short: 'Sharpe',
		description:
			'Annualised mean over sample standard deviation of one-bar returns (zero risk-free rate).',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [windowParam(60), periodsPerYearParam()],
		outputs: VALUE,
		compute: (d, p) => {
			const r = pctChange(d.close);
			const mean = rollingMean(r, p.window);
			const sd = rollingStd(r, p.window, 1);
			const k = Math.sqrt(p.periodsPerYear);
			return [
				scale(
					zip(mean, sd, (m, s) => (s > 1e-12 * Math.abs(m) ? m / s : NaN)),
					k
				)
			];
		}
	},
	{
		id: 'sortino',
		name: 'Rolling Sortino Ratio',
		short: 'Sortino',
		description:
			'Annualised mean return over downside deviation (root mean square of negative returns).',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [windowParam(60), periodsPerYearParam()],
		outputs: VALUE,
		compute: (d, p) => {
			const r = pctChange(d.close);
			const mean = rollingMean(r, p.window);
			const downside = map(
				rollingMean(
					map(r, (x) => (x < 0 ? x * x : x >= 0 ? 0 : NaN)),
					p.window
				),
				Math.sqrt
			);
			const k = Math.sqrt(p.periodsPerYear);
			return [
				scale(
					zip(mean, downside, (m, s) => (s > 1e-12 * Math.abs(m) ? m / s : NaN)),
					k
				)
			];
		}
	},
	{
		id: 'drawdown',
		name: 'Drawdown from Running Peak',
		short: 'DD',
		description: 'Percent decline of the close from its highest close so far (0 at new highs).',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [],
		outputs: VALUE,
		compute: (d) => [drawdownFromPeak(d.close)]
	},
	{
		id: 'max_drawdown',
		name: 'Rolling Max Drawdown',
		short: 'MaxDD',
		description: 'Worst peak-to-trough percent decline of the close inside the last N bars.',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [windowParam(60, 2, 500)],
		outputs: VALUE,
		compute: (d, p) => [rollingMaxDrawdown(d.close, p.window)]
	},
	{
		id: 'highest_high',
		name: 'N-Bar High',
		short: 'HH',
		description: 'Highest high of the last N bars, including the current bar.',
		category: 'Statistics',
		pane: 'price',
		params: [int('period', 'Period', 20, 1, 1000)],
		outputs: VALUE,
		compute: (d, p) => [rollingMax(d.high, p.period)]
	},
	{
		id: 'lowest_low',
		name: 'N-Bar Low',
		short: 'LL',
		description: 'Lowest low of the last N bars, including the current bar.',
		category: 'Statistics',
		pane: 'price',
		params: [int('period', 'Period', 20, 1, 1000)],
		outputs: VALUE,
		compute: (d, p) => [rollingMin(d.low, p.period)]
	},
	{
		id: 'distance_from_high',
		name: 'Distance from N-Bar High %',
		short: 'Dist HH',
		description:
			'Percent by which the close sits below the highest high of the last N bars (0 or negative).',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [int('period', 'Period', 20, 1, 1000)],
		outputs: VALUE,
		compute: (d, p) => [pctDiff(d.close, rollingMax(d.high, p.period))]
	},
	{
		id: 'distance_from_low',
		name: 'Distance from N-Bar Low %',
		short: 'Dist LL',
		description:
			'Percent by which the close sits above the lowest low of the last N bars (0 or positive).',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [int('period', 'Period', 20, 1, 1000)],
		outputs: VALUE,
		compute: (d, p) => [pctDiff(d.close, rollingMin(d.low, p.period))]
	},
	{
		id: 'autocorrelation',
		name: 'Rolling Return Autocorrelation',
		short: 'ACF',
		description:
			'Correlation between one-bar returns and returns L bars earlier over N bars (-1 to 1).',
		category: 'Statistics',
		pane: 'separate',
		guides: [0],
		params: [windowParam(30, 3, 500), int('lag', 'Lag', 1, 1, 50)],
		outputs: VALUE,
		compute: (d, p) => [rollingAutocorrelation(pctChange(d.close), p.window, p.lag)]
	},
	{
		id: 'up_bar_ratio',
		name: 'Up-Bar Ratio',
		short: 'Up %',
		description: 'Percent of the last N bars that closed above the previous close.',
		category: 'Statistics',
		pane: 'separate',
		guides: [50],
		params: [windowParam(20)],
		outputs: VALUE,
		compute: (d, p) => {
			const up = pctChange(d.close);
			const flag = map(up, (x) => (x > 0 ? 1 : x <= 0 ? 0 : NaN));
			return [clamp(scale(rollingMean(flag, p.window), 100), 0, 100)];
		}
	}
];
