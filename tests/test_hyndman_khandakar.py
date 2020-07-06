from hyndman_khandakar import HyndmanKhandakar
import numpy as np
import pandas as pd
import statsmodels.api as sm


def test_hyndman_khandakar():
    rg = np.random.default_rng(0)

    # Generate data from ARIMA(2, 0, 1) + 100 model
    ar = np.array([1, 0.6, -0.3])
    ma = np.array([1, 0.3])
    y = sm.tsa.arma_generate_sample(
        ar, ma,
        distrvs=rg.standard_normal,
        nsample=100, burnin=500
    ) + 100

    # Ensure model is stationary and invertible
    assert all([-1 < ar[2] < 1, ar[1] + ar[2] < 1, ar[2] - ar[1] < 1])
    assert -1 < ma[1] < 1

    index = pd.date_range(start="2020-01-01", periods=len(y), freq="D")
    ts = pd.Series(y, index=index)
    hk = HyndmanKhandakar(ts)
    hk.find(verbose=1)

    assert hk.order["p"] == 2
    assert hk.order["d"] == 0
    assert hk.order["q"] == 1
    assert hk.order["trend"] == "c"
