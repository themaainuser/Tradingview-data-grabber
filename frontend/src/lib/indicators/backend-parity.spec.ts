/**
 * Golden values derived offline with the backend's own `analytics.add_indicators` (pandas 3.0.6,
 * numpy 2.5.3) on the seeded series produced by `makeOhlcv(240, 42)`. Values are rounded to 12
 * significant digits. `first` is the exact warm-up index (pandas `min_periods`).
 */
import { describe, expect, it } from 'vitest';
import { makeOhlcv } from './fixtures';
import { computeIndicator, getIndicator } from './registry';

const N = 240;
const data = makeOhlcv(N, 42);

interface Golden {
	first: number;
	values: Record<number, number>;
}

/** Columns of `add_indicators` (sma_20 ... vwap). */
const BACKEND: Record<string, Golden> = {
	sma_20: {
		first: 19,
		values: {
			19: 97.3643731108,
			20: 97.1874539601,
			25: 96.4189319882,
			26: 96.3235151347,
			32: 95.6438839428,
			33: 95.5859682139,
			34: 95.4854704401,
			60: 94.6417974616,
			120: 105.524038595,
			239: 114.002661444
		}
	},
	ema_20: {
		first: 19,
		values: {
			19: 97.1417938007,
			20: 97.1155307713,
			25: 96.9505790463,
			26: 96.8485573391,
			32: 95.5238586585,
			33: 95.3405169097,
			34: 95.1683372616,
			60: 93.9933113852,
			120: 106.010528786,
			239: 114.501412165
		}
	},
	ema_12: {
		first: 11,
		values: {
			18: 96.6622754659,
			19: 96.5038310253,
			20: 96.559554251,
			25: 96.5895337331,
			26: 96.4802748696,
			32: 94.9000978905,
			33: 94.6998936453,
			34: 94.520314716,
			60: 93.535129152,
			120: 107.223615235,
			239: 114.990137868
		}
	},
	ema_26: {
		first: 25,
		values: {
			25: 97.2502910866,
			26: 97.148739978,
			32: 95.9439551869,
			33: 95.7702377876,
			34: 95.6044891075,
			60: 94.2658679645,
			120: 105.333227369,
			239: 114.346298469
		}
	},
	rsi_14: {
		first: 14,
		values: {
			18: 44.7058783018,
			19: 41.6716888703,
			20: 48.1813463715,
			25: 41.5153458999,
			26: 45.1879455553,
			32: 46.3345049754,
			33: 41.3107012592,
			34: 41.0877596934,
			60: 50.0181516347,
			120: 69.6480243864,
			239: 54.9575906218
		}
	},
	macd: {
		first: 25,
		values: {
			25: -0.660757353557,
			26: -0.668465108425,
			32: -1.04385729641,
			33: -1.07034414235,
			34: -1.08417439143,
			60: -0.730738812474,
			120: 1.89038786613,
			239: 0.643839398878
		}
	},
	macd_signal: {
		first: 33,
		values: {
			33: -0.992375811948,
			34: -1.01073552784,
			60: -0.623194562161,
			120: 1.42035908692,
			239: 0.401297493956
		}
	},
	macd_hist: {
		first: 33,
		values: {
			33: -0.0779683303985,
			34: -0.0734388635852,
			60: -0.107544250312,
			120: 0.470028779214,
			239: 0.242541904923
		}
	},
	atr_14: {
		first: 13,
		values: {
			18: 2.29305712438,
			19: 2.23538681734,
			20: 2.22028741915,
			25: 2.23185004129,
			26: 2.17520639929,
			32: 2.02917589025,
			33: 2.02966163791,
			34: 1.9486393703,
			60: 1.88444110731,
			120: 1.85964390456,
			239: 1.66745760436
		}
	},
	bb_lower: {
		first: 19,
		values: {
			19: 93.2535844234,
			20: 93.3177408032,
			25: 93.9407658484,
			26: 93.9176014398,
			32: 92.6278746631,
			33: 92.4615305852,
			34: 92.2351513864,
			60: 90.7424283213,
			120: 100.740390602,
			239: 110.279041105
		}
	},
	bb_middle: {
		first: 19,
		values: {
			19: 97.3643731108,
			20: 97.1874539601,
			25: 96.4189319882,
			26: 96.3235151347,
			32: 95.6438839428,
			33: 95.5859682139,
			34: 95.4854704401,
			60: 94.6417974616,
			120: 105.524038595,
			239: 114.002661444
		}
	},
	bb_upper: {
		first: 19,
		values: {
			19: 101.475161798,
			20: 101.057167117,
			25: 98.897098128,
			26: 98.7294288296,
			32: 98.6598932224,
			33: 98.7104058426,
			34: 98.7357894938,
			60: 98.5411666019,
			120: 110.307686589,
			239: 117.726281782
		}
	},
	vwap: {
		first: 0,
		values: {
			0: 100.314548714,
			10: 98.3990702269,
			18: 97.2680721797,
			19: 97.2113832457,
			20: 97.1677774046,
			25: 97.1465809286,
			26: 97.1028662074,
			32: 96.4931000508,
			33: 96.4482531518,
			34: 96.3082384389,
			60: 95.3700068055,
			120: 98.7292720319,
			239: 106.959155688
		}
	}
};

/** pandas / numpy reference values for the statistics that follow pandas conventions. */
const EXTRA: Record<string, Golden> = {
	skew60: { first: 60, values: { 60: 0.147162133126, 100: -0.244726073255, 239: 0.191253269481 } },
	kurt60: { first: 60, values: { 60: -1.29203130325, 100: -1.02690824238, 239: -0.856301557705 } },
	zscore20: {
		first: 19,
		values: {
			30: -0.945477192982,
			59: -0.657842020475,
			60: -0.172259600302,
			100: -1.07360244713,
			239: 0.783692267224
		}
	},
	stdret20: {
		first: 20,
		values: {
			30: 1.27859787122,
			59: 1.2207181309,
			60: 1.20753732255,
			100: 1.22104541927,
			239: 1.05491270376
		}
	},
	histvol20: {
		first: 20,
		values: {
			30: 20.3075886943,
			59: 19.3655549817,
			60: 19.1584479742,
			100: 19.4092617071,
			239: 16.7009594542
		}
	},
	sharpe60: { first: 60, values: { 60: -1.29509703859, 100: 1.39839128786, 239: 0.601893061463 } },
	autocorr30: {
		first: 31,
		values: {
			59: -0.373154751481,
			60: -0.349812460653,
			100: -0.0514812266663,
			239: -0.202949312645
		}
	},
	linregSlope20: {
		first: 19,
		values: {
			30: -0.071167646339,
			59: -0.241800846281,
			60: -0.242627453626,
			100: 0.0155787261208,
			239: 0.269096112398
		}
	},
	linregValue20: {
		first: 19,
		values: {
			30: 94.8976011284,
			59: 92.3780675345,
			60: 92.3368366522,
			100: 101.745215296,
			239: 116.559074511
		}
	},
	linregR2020: {
		first: 19,
		values: {
			30: 0.0675077590636,
			59: 0.511667987987,
			60: 0.514923628497,
			100: 0.00972250258428,
			239: 0.694601473965
		}
	},
	wma10: {
		first: 9,
		values: {
			30: 94.4776423002,
			59: 92.6405602527,
			60: 92.8454185288,
			100: 101.72074536,
			239: 115.510765639
		}
	},
	prank50: { first: 50, values: { 59: 20.0, 60: 34.0, 100: 42.0, 239: 60.0 } }
};

function run(id: string, overrides: Record<string, unknown>, output = 0): Float64Array {
	const def = getIndicator(id);
	if (!def) throw new Error(`unknown indicator ${id}`);
	return computeIndicator(def, data, overrides)[output];
}

function expectGolden(actual: Float64Array, golden: Golden, relTol: number) {
	expect(actual).toHaveLength(N);
	expect(actual.findIndex((x) => Number.isFinite(x))).toBe(golden.first);
	for (const [index, expected] of Object.entries(golden.values)) {
		const got = actual[Number(index)];
		expect(Math.abs(got - expected), `index ${index}: ${got} vs ${expected}`).toBeLessThanOrEqual(
			relTol * Math.abs(expected)
		);
	}
}

describe('seeded fixture', () => {
	it('reproduces the series used to derive the pandas goldens', () => {
		const sum = data.close.reduce((a, b) => a + b, 0);
		expect(Math.abs(sum - 25648.5648141)).toBeLessThan(1e-6);
		expect(Math.abs(data.close[239] - 115.499652332)).toBeLessThan(1e-9);
	});
});

describe('backend parity (analytics.add_indicators)', () => {
	const cases: [string, string, Record<string, unknown>, number][] = [
		['sma_20', 'sma', { period: 20 }, 0],
		['ema_20', 'ema', { period: 20 }, 0],
		['ema_12', 'ema', { period: 12 }, 0],
		['ema_26', 'ema', { period: 26 }, 0],
		['rsi_14', 'rsi', { period: 14 }, 0],
		['macd', 'macd', { fast: 12, slow: 26, signal: 9 }, 0],
		['macd_signal', 'macd', { fast: 12, slow: 26, signal: 9 }, 1],
		['macd_hist', 'macd', { fast: 12, slow: 26, signal: 9 }, 2],
		['atr_14', 'atr', { period: 14 }, 0],
		['bb_lower', 'bollinger', { period: 20, mult: 2 }, 0],
		['bb_middle', 'bollinger', { period: 20, mult: 2 }, 1],
		['bb_upper', 'bollinger', { period: 20, mult: 2 }, 2],
		['vwap', 'vwap', {}, 0]
	];
	it.each(cases)(
		'%s matches pandas to 1e-9 relative incl. warm-up index',
		(column, id, params, out) => {
			expectGolden(run(id, params, out), BACKEND[column], 1e-9);
		}
	);
});

describe('pandas-convention statistics', () => {
	const cases: [string, string, Record<string, unknown>][] = [
		['skew60', 'skew', { window: 60 }],
		['kurt60', 'kurtosis', { window: 60 }],
		['zscore20', 'zscore', { window: 20 }],
		['stdret20', 'stdev_returns', { window: 20 }],
		['histvol20', 'hist_vol', { window: 20, periodsPerYear: 252 }],
		['sharpe60', 'sharpe', { window: 60, periodsPerYear: 252 }],
		['autocorr30', 'autocorrelation', { window: 30, lag: 1 }],
		['linregSlope20', 'linreg_slope', { period: 20 }],
		['linregValue20', 'linreg', { period: 20 }],
		['linregR2020', 'linreg_r2', { period: 20 }],
		['wma10', 'wma', { period: 10 }],
		['prank50', 'percent_rank', { window: 50 }]
	];
	it.each(cases)('%s matches pandas/numpy', (column, id, params) => {
		expectGolden(run(id, params), EXTRA[column], 1e-8);
	});
});
