"""
Management command: train (or retrain) the LightGBM property valuation model.

Usage:
    python manage.py train_valuation_model
    python manage.py train_valuation_model --min-samples 20
"""
import pickle
import numpy as np
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from listings.models import Listing
from listings.services.valuation import MODEL_PATH, FEATURE_COLS, CAT_COLS, invalidate_cache

ELIGIBLE_CATEGORIES = {'properties', 'rentals', 'buy_sell'}
ELIGIBLE_STATUSES   = {'active', 'sold', 'under_contract', 'draft', 'pending'}
MIN_SAMPLES_DEFAULT = 10


class Command(BaseCommand):
    help = 'Train the LightGBM property valuation model on current listing data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-samples', type=int, default=MIN_SAMPLES_DEFAULT,
            help=f'Minimum listings required to train (default: {MIN_SAMPLES_DEFAULT})',
        )

    def handle(self, *args, **options):
        try:
            import lightgbm as lgb
        except ImportError:
            raise CommandError(
                'lightgbm is not installed. Run: pip install lightgbm'
            )

        min_samples = options['min_samples']

        self.stdout.write('Querying listings…')
        qs = Listing.objects.filter(
            price__isnull=False,
            price__gt=0,
            category__in=ELIGIBLE_CATEGORIES,
            status__in=ELIGIBLE_STATUSES,
        ).values(
            'price', 'square_footage', 'bedrooms', 'year_built',
            'hoa_fee', 'bills_included', 'zip_code', 'city',
            'property_type', 'category', 'accommodation_type',
        )

        rows = list(qs)
        if len(rows) < min_samples:
            raise CommandError(
                f'Only {len(rows)} eligible listing(s) found — need at least {min_samples}. '
                f'Add more listings or lower --min-samples.'
            )

        self.stdout.write(f'Building feature matrix from {len(rows)} listings…')

        # Build plain lists (avoid pandas import requirement at runtime)
        prices           = []
        feature_matrix   = []
        encoders         = {col: {} for col in CAT_COLS}

        for row in rows:
            # Encode categoricals: assign an int id per unique value
            for col in CAT_COLS:
                val = row[col] or ''
                if val not in encoders[col]:
                    encoders[col][val] = len(encoders[col])

        for row in rows:
            prices.append(float(row['price']))
            feat = {
                'square_footage': float(row['square_footage']) if row['square_footage'] else np.nan,
                'bedrooms':       float(row['bedrooms'])       if row['bedrooms']       else np.nan,
                'year_built':     float(row['year_built'])     if row['year_built']     else np.nan,
                'hoa_fee':        float(row['hoa_fee'])        if row['hoa_fee']        else 0.0,
                'bills_included': int(row['bills_included']),
            }
            for col in CAT_COLS:
                val = row[col] or ''
                feat[col] = encoders[col].get(val, -1)

            feature_matrix.append([feat[c] for c in FEATURE_COLS])

        X = np.array(feature_matrix, dtype=np.float64)
        y = np.log1p(np.array(prices, dtype=np.float64))

        self.stdout.write('Training LightGBM…')
        model = lgb.LGBMRegressor(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=max(3, len(rows) // 20),
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
        )
        model.fit(X, y)

        # In-sample MAPE as a proxy for confidence bands
        preds   = np.expm1(model.predict(X))
        actuals = np.array(prices)
        mape    = float(np.mean(np.abs((actuals - preds) / actuals)))

        n = len(rows)
        confidence = 'high' if n >= 500 else 'medium' if n >= 50 else 'low'

        self.stdout.write(f'  Samples : {n}')
        self.stdout.write(f'  MAPE    : {mape:.1%}')
        self.stdout.write(f'  Margin  : ±{max(mape, 0.05):.1%}')
        self.stdout.write(f'  Confidence : {confidence}')

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MODEL_PATH, 'wb') as f:
            pickle.dump({
                'model':       model,
                'encoders':    encoders,
                'feature_cols': FEATURE_COLS,
                'margin_pct':  max(mape, 0.05),
                'n_samples':   n,
                'confidence':  confidence,
            }, f)

        invalidate_cache()
        self.stdout.write(self.style.SUCCESS(f'Model saved → {MODEL_PATH}'))
