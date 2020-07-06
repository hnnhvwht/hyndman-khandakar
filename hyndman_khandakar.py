import numpy as np
import statsmodels.api as sm
from statsmodels.tools.sm_exceptions import InterpolationWarning
from warnings import catch_warnings, simplefilter, warn


class HyndmanKhandakar:
    """
    Object that finds and stores the best ARIMA(p, d, q) model for a time
    series by minimizing the Akaike information criterion with correction for
    small sample sizes.

    Parameters
    ----------
    ts : pandas.Series
        The (datetime-indexed) time series
    alpha : float, optional, default: 0.05
        Type I error rate ("significance" level)
    conditions : tuple, optional, default: (5, 1.001)
        Criteria for the complex roots of the AR and MA polynomials:
            0: the upper bound (inclusive) for each of p and q
            1: the lower bound (exclusive) for each complex root's modulus
    full_search : bool, optional, default: False
        Whether to perform an exhaustive search of all possible orders up to
        the upper bound for each of p and q in `conditions`
    verbose : int, optional, default: 0
        Whether to display warnings and fitting details. If 0, all warnings
        are suppressed and no fitting details are displayed. Otherwise,
        warnings are displayed and the value is passed to the `disp` keyword
        of the statsmodels.tsa.arima_model.ARIMA.fit() method.

    Attributes
    ----------
    model : statsmodels.tsa.arima.model.ARIMAResults
    order : dict
        Order of the model in the form
        {"p": int, "d": int, "q": int, "trend": str {"c", "nc"}}
    aicc : float
        Akaike information criterion with correction for small sample sizes
        for the best model
    p_values : dict
        A dictionary of dictionaries containing the p-value for the ADF and
        KPSS tests for each degree of differencing (up to 2)

    References
    ----------
    R. J. Hyndman and Y. Khandakar, "Automatic Time Series Forecasting: The
    forecast Package for R," J. Stat. Software, vol. 27, no. 3, Jul. 2008.
    Available doi: 10.18637/jss.v027.i03
    """
    def __init__(self, ts, alpha=0.05, conditions=(5, 1.001),
                 full_search=False, verbose=0):
        self.ts = ts
        self.alpha = alpha
        self.conditions = conditions
        self.full_search = full_search
        self.verbose = verbose
        self.model = None
        self.order = {"p": 0, "d": 0, "q": 0, "trend": "nc"}
        self.aicc = np.inf
        self.p_values = dict()

    def _get_differencing_degree(self):
        """
        Iteratively apply the augmented Dicker-Fuller (ADF) and Kwiatkowski-
        Phillips-Schmidt-Shin (KPSS) tests to determine the degree of
        differencing for a time series. Note: The original Hyndman-Khandakar
        algorithm uses only the KPSS test.
        """
        def _test(ts):
            _, p_adf, *rest = sm.tsa.stattools.adfuller(ts)
            _, p_kpss, *rest = sm.tsa.stattools.kpss(ts, nlags="auto")
            if p_kpss < self.alpha or p_adf >= self.alpha:
                if self.d == 2:
                    if self.verbose:
                        warn("Failed to stationarize mean by differencing. "
                             + "Continuing with d = 2...", UserWarning)
                    return
                ts_diff = ts.diff().dropna()
                self.p_values[self.d] = {"adf": p_adf, "kpss": p_kpss}
                self.d += 1
                _test(ts_diff)
            else:
                return

        if not self.verbose:
            with catch_warnings():
                simplefilter("ignore", category=InterpolationWarning)
                _test(self.ts)
        else:
            _test(self.ts)

    def _correct_aic(self, order, trend, aic):
        """
        Calculate the Akaike information criterion (AIC) with correction for
        small sample sizes for an ARIMA(p, d, q) model.

        Parameters
        ----------
        aic : float
            The Akaike information criterion

        Returns
        -------
        float

        References
        ----------
        K. P. Burnham and D. R. Anderson, "Multimodel Inference: Understanding
        AIC and BIC in Model Selection," Sociol. Methods Res., vol. 33, no. 2,
        pp. 261-304, Nov. 2004. Available doi: 10.1177/0049124104268644
        """
        k = 1 if trend == "c" else 0
        n = order[0] + order[2] + k + 1
        return aic + 2 * n * (n + 1) / (len(self.ts) - n - 1)

    def _fit(self, order, trend, **fit_kargs):
        """
        Fit an ARIMA model of a given order and trend to the data. Store the
        model if it presents the smallest AICc up to this point and satisfies
        the conditions for invertibility and stationarity.

        Parameters
        ----------
        fit_kargs : dict, optional
            Arguments to pass to sm.tsa.ARIMA().fit() within self._fit()
        """
        model = sm.tsa.ARIMA(self.ts, order=order)
        model = model.fit(trend=trend, disp=self.verbose, **fit_kargs)
        aicc = self._correct_aic(order, trend, model.aic)
        if aicc < self.aicc:
            invertible = all(np.abs(model.arroots) > self.conditions[1])
            stationary = all(np.abs(model.maroots) > self.conditions[1])
            if invertible and stationary:
                self.model = model
                self.order["p"] = order[0]
                self.order["d"] = order[1]
                self.order["q"] = order[2]
                self.order["trend"] = trend
                self.aicc = aicc

    def find(self, **fit_kargs):
        self._get_differencing_degree()
        d = self.order["d"]

        if self.full_search:
            orders = []
            p_candidates = np.arange(self.conditions[0] + 1)
            q_candidates = np.arange(self.conditions[0] + 1)

        else:
            if d <= 1:
                orders = [
                    ((0, d, 0), "c"),
                    ((0, d, 0), "nc"),
                    ((1, d, 0), "c"),
                    ((0, d, 1), "c"),
                    ((2, d, 2), "c")
                ]

            else:
                orders = [
                    ((0, d, 0), "nc"),
                    ((1, d, 0), "nc"),
                    ((0, d, 1), "nc"),
                    ((2, d, 2), "nc")
                ]

            for (order, trend) in orders:
                try:
                    self._fit(order, trend, **fit_kargs)
                except ValueError:
                    continue

            best_p = self.order["p"]
            p_candidates = [p for p in np.arange(best_p - 1, best_p + 2)
                            if not p < 0 or not p > self.conditions[0]]

            best_q = self.order["q"]
            q_candidates = [q for q in np.arange(best_q - 1, best_q + 2)
                            if not q < 0 or not q > self.conditions[0]]

        for p in p_candidates:
            for q in q_candidates:
                for trend in ("c", "nc"):
                    order = (p, d, q)
                    if (order, trend) in orders:
                        pass
                    else:
                        try:
                            self._fit(order, trend, **fit_kargs)
                            orders.append((order, trend))
                        except ValueError:
                            continue
