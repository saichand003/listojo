"""
LightGBM property valuation service.

Train:   python manage.py train_valuation_model
Predict: valuation.predict_price(listing) → {estimate, low, high, confidence, n_samples}
"""
import logging
import pickle
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_PATH = Path(settings.BASE_DIR) / 'listings' / 'ml' / 'valuation_model.pkl'

FEATURE_COLS = [
    'square_footage', 'bedrooms', 'year_built', 'hoa_fee',
    'bills_included', 'zip_code', 'city', 'property_type',
    'category', 'accommodation_type',
]

CAT_COLS = ['zip_code', 'city', 'property_type', 'category', 'accommodation_type']

_cache = {}


def _load_model():
    if 'data' in _cache:
        return _cache['data']
    if not MODEL_PATH.exists():
        return None
    try:
        with open(MODEL_PATH, 'rb') as f:
            _cache['data'] = pickle.load(f)
        return _cache['data']
    except Exception:
        logger.exception('Failed to load valuation model from %s', MODEL_PATH)
        return None


def invalidate_cache():
    _cache.clear()


def predict_price(listing):
    """
    Return a price estimate dict or None if the model is not trained yet.

    Return shape:
        {estimate: int, low: int, high: int,
         confidence: str, n_samples: int}
    """
    import numpy as np

    model_data = _load_model()
    if model_data is None:
        return None

    try:
        model    = model_data['model']
        encoders = model_data['encoders']

        row = {
            'square_footage': float(listing.square_footage) if listing.square_footage else np.nan,
            'bedrooms':       float(listing.bedrooms)       if listing.bedrooms       else np.nan,
            'year_built':     float(listing.year_built)     if listing.year_built     else np.nan,
            'hoa_fee':        float(listing.hoa_fee)        if listing.hoa_fee        else 0.0,
            'bills_included': int(listing.bills_included),
        }

        for col in CAT_COLS:
            val = getattr(listing, col, '') or ''
            row[col] = encoders.get(col, {}).get(val, -1)

        X = [[row[col] for col in FEATURE_COLS]]

        log_pred  = model.predict(X)[0]
        predicted = float(np.expm1(log_pred))

        margin    = model_data.get('margin_pct', 0.08)
        is_rental = getattr(listing, 'price_unit', '') in ('mo', 'wk', 'day', 'hr')
        rounding  = 50 if is_rental else 1000

        def snap(v):
            return int(round(v / rounding) * rounding)

        return {
            'estimate':   snap(predicted),
            'low':        snap(predicted * (1 - margin)),
            'high':       snap(predicted * (1 + margin)),
            'confidence': model_data.get('confidence', 'low'),
            'n_samples':  model_data.get('n_samples', 0),
        }

    except Exception:
        logger.exception('Valuation prediction failed for listing pk=%s', getattr(listing, 'pk', '?'))
        return None
