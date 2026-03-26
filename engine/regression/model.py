"""
Creative Regression Model — decomposes ad performance into creative element coefficients.

This is the brain of the system. It answers: which creative elements actually drive
first-note completions, and which are noise?

Approach:
1. Encode each ad's MECE taxonomy into feature vectors (one-hot for categoricals)
2. Dependent variable: cost_per_first_note (lower = better)
3. Run OLS with VIF checks for multicollinearity
4. Output: ranked coefficients with significance levels

MECE is critical here. If taxonomy categories overlap, you get covariance problems
and the coefficients become uninterpretable. The taxonomy in models.py is designed
to be orthogonal across dimensions — but the intern should validate this empirically
with VIF scores on real data.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from engine.models import AdVariant, ExistingAd, PerformanceSnapshot, RegressionResult
from engine.store import Store


# Taxonomy dimensions that get one-hot encoded
CATEGORICAL_FEATURES = [
    "message_type",
    "hook_type",
    "cta_type",
    "tone",
    "visual_style",
    "subject_matter",
    "color_mood",
    "text_density",
    "format",
    "platform",
    "placement",
]

# Numerical features used directly
NUMERICAL_FEATURES = [
    "headline_word_count",
    "copy_reading_level",
]

# Boolean features (0/1)
BOOLEAN_FEATURES = [
    "uses_number",
    "uses_question",
    "uses_first_person",
    "uses_social_proof",
]


class CreativeRegressionModel:
    def __init__(self, store: Store):
        self.store = store

    def build_dataset(self, include_existing: bool = True) -> pd.DataFrame:
        """
        Build the regression dataset by joining variant taxonomy with performance data.
        Each row = one ad variant with aggregated performance metrics.
        When include_existing=True, also incorporates imported Meta/Google ads.
        """
        rows = []

        # Engine-generated variants (need snapshot aggregation)
        for variant in self.store.get_all_variants():
            snapshots = self.store.get_snapshots_for_variant(variant.id)
            if not snapshots:
                continue

            total_spend = sum(s.spend for s in snapshots)
            total_first_notes = sum(s.first_note_completions for s in snapshots)
            total_impressions = sum(s.impressions for s in snapshots)
            total_clicks = sum(s.clicks for s in snapshots)

            if total_spend < 20 or total_impressions < 100:
                continue

            cpa = total_spend / total_first_notes if total_first_notes > 0 else None
            conversion_rate = total_first_notes / total_clicks if total_clicks > 0 else 0
            ctr = total_clicks / total_impressions if total_impressions > 0 else 0

            tax = variant.taxonomy
            rows.append(self._taxonomy_row(
                variant_id=variant.id, cpa=cpa, conversion_rate=conversion_rate,
                ctr=ctr, total_spend=total_spend, total_first_notes=total_first_notes,
                tax=tax,
            ))

        # Imported existing ads (performance is pre-aggregated)
        if include_existing:
            for ad in self.store.get_existing_ads_with_taxonomy():
                if ad.spend < 20 or ad.impressions < 100:
                    continue

                cpa = ad.cost_per_conversion
                conversion_rate = ad.conversions / ad.clicks if ad.clicks > 0 else 0
                ctr = ad.ctr

                rows.append(self._taxonomy_row(
                    variant_id=ad.id, cpa=cpa, conversion_rate=conversion_rate,
                    ctr=ctr, total_spend=ad.spend, total_first_notes=ad.conversions,
                    tax=ad.taxonomy,
                ))

        return pd.DataFrame(rows)

    @staticmethod
    def _taxonomy_row(
        variant_id: str, cpa, conversion_rate: float, ctr: float,
        total_spend: float, total_first_notes: int, tax,
    ) -> dict:
        return {
            "variant_id": variant_id,
            "cost_per_first_note": cpa,
            "conversion_rate": conversion_rate,
            "ctr": ctr,
            "total_spend": total_spend,
            "total_first_notes": total_first_notes,
            "message_type": tax.message_type,
            "hook_type": tax.hook_type,
            "cta_type": tax.cta_type,
            "tone": tax.tone,
            "visual_style": tax.visual_style,
            "subject_matter": tax.subject_matter,
            "color_mood": tax.color_mood,
            "text_density": tax.text_density,
            "format": tax.format.value if hasattr(tax.format, "value") else str(tax.format),
            "platform": tax.platform.value if hasattr(tax.platform, "value") else str(tax.platform),
            "placement": tax.placement,
            "headline_word_count": tax.headline_word_count,
            "copy_reading_level": tax.copy_reading_level,
            "uses_number": int(tax.uses_number),
            "uses_question": int(tax.uses_question),
            "uses_first_person": int(tax.uses_first_person),
            "uses_social_proof": int(tax.uses_social_proof),
        }

    def encode_features(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """
        One-hot encode categorical features. Returns encoded DataFrame and feature names.
        Uses drop_first=True to avoid the dummy variable trap.
        """
        encoded = pd.get_dummies(
            df[CATEGORICAL_FEATURES],
            columns=CATEGORICAL_FEATURES,
            drop_first=True,
            dtype=int,
        )

        # Add numerical and boolean features
        for col in NUMERICAL_FEATURES + BOOLEAN_FEATURES:
            if col in df.columns:
                encoded[col] = df[col]

        feature_names = list(encoded.columns)
        return encoded, feature_names

    def calculate_vif(self, X: pd.DataFrame) -> dict[str, float]:
        """
        Calculate Variance Inflation Factor for each feature.
        VIF > 5 suggests problematic multicollinearity.
        VIF > 10 means the feature is almost certainly redundant.
        """
        from numpy.linalg import LinAlgError

        vif_scores = {}
        for i, col in enumerate(X.columns):
            try:
                other_cols = [c for j, c in enumerate(X.columns) if j != i]
                if not other_cols:
                    vif_scores[col] = 1.0
                    continue

                y = X[col].values
                x = X[other_cols].values

                # Add constant
                x = np.column_stack([np.ones(len(x)), x])

                # OLS
                beta = np.linalg.lstsq(x, y, rcond=None)[0]
                y_hat = x @ beta
                ss_res = np.sum((y - y_hat) ** 2)
                ss_tot = np.sum((y - np.mean(y)) ** 2)

                r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                vif = 1 / (1 - r_squared) if r_squared < 1 else float("inf")
                vif_scores[col] = round(vif, 2)

            except (LinAlgError, ZeroDivisionError):
                vif_scores[col] = float("inf")

        return vif_scores

    def run(self, target: str = "cost_per_first_note", min_observations: int = 10) -> Optional[RegressionResult]:
        """
        Run the full regression analysis.

        target: which metric to model. Default is cost_per_first_note.
        Can also use "conversion_rate" or "ctr".
        """
        df = self.build_dataset()

        if len(df) < min_observations:
            print(f"Only {len(df)} observations — need at least {min_observations} for meaningful regression.")
            return None

        df = df.dropna(subset=[target])
        if len(df) < min_observations:
            return None

        y = df[target].values
        X_encoded, feature_names = self.encode_features(df)

        # Drop features with zero variance
        non_zero_var = X_encoded.columns[X_encoded.var() > 0]
        X_encoded = X_encoded[non_zero_var]
        feature_names = list(non_zero_var)

        # Add constant for intercept
        X = np.column_stack([np.ones(len(X_encoded)), X_encoded.values])
        all_names = ["intercept"] + feature_names

        # OLS regression
        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            print("Regression failed — singular matrix. Check for perfect multicollinearity.")
            return None

        # Predictions and residuals
        y_hat = X @ beta
        residuals = y - y_hat
        n, k = X.shape

        # R-squared
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        adj_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - k - 1) if n > k + 1 else 0

        # Standard errors and p-values
        mse = ss_res / (n - k) if n > k else ss_res
        try:
            var_beta = mse * np.linalg.inv(X.T @ X)
            se = np.sqrt(np.abs(np.diag(var_beta)))
        except np.linalg.LinAlgError:
            se = np.full(k, np.nan)

        t_stats = beta / se
        p_values = [2 * (1 - scipy_stats.t.cdf(abs(t), df=n - k)) for t in t_stats]

        # Confidence intervals
        t_crit = scipy_stats.t.ppf(0.975, df=n - k)
        ci = {
            name: (float(beta[i] - t_crit * se[i]), float(beta[i] + t_crit * se[i]))
            for i, name in enumerate(all_names)
        }

        # Build coefficient dict (skip intercept for reporting)
        coefficients = {name: float(beta[i]) for i, name in enumerate(all_names) if name != "intercept"}
        p_vals = {name: float(p_values[i]) for i, name in enumerate(all_names) if name != "intercept"}

        # VIF scores
        vif_scores = self.calculate_vif(X_encoded)

        # Durbin-Watson statistic
        diffs = np.diff(residuals)
        dw = float(np.sum(diffs ** 2) / ss_res) if ss_res > 0 else 0

        # Condition number
        cond = float(np.linalg.cond(X))

        # Sort features by effect
        sig_features = {k: v for k, v in coefficients.items() if p_vals.get(k, 1) < 0.05}
        insig_features = [k for k, v in p_vals.items() if v >= 0.05]

        # For CPA, negative coefficient = good (lowers cost)
        # For conversion_rate/CTR, positive = good
        if target == "cost_per_first_note":
            top_positive = sorted([k for k, v in sig_features.items() if v < 0], key=lambda k: sig_features[k])[:10]
            top_negative = sorted([k for k, v in sig_features.items() if v > 0], key=lambda k: -sig_features[k])[:10]
        else:
            top_positive = sorted([k for k, v in sig_features.items() if v > 0], key=lambda k: -sig_features[k])[:10]
            top_negative = sorted([k for k, v in sig_features.items() if v < 0], key=lambda k: sig_features[k])[:10]

        return RegressionResult(
            run_date=date.today(),
            n_observations=n,
            r_squared=round(r_squared, 4),
            adjusted_r_squared=round(adj_r_squared, 4),
            coefficients=coefficients,
            p_values=p_vals,
            confidence_intervals=ci,
            top_positive_features=top_positive,
            top_negative_features=top_negative,
            insignificant_features=insig_features,
            vif_scores=vif_scores,
            durbin_watson=round(dw, 4),
            condition_number=round(cond, 2),
        )

    def get_creative_playbook(self) -> dict:
        """
        Generate a human-readable playbook from the latest regression results.
        Returns structured insights for the creative team.
        """
        result = self.run()
        if not result:
            return {"status": "insufficient_data", "message": "Need more ad performance data."}

        playbook = {
            "model_quality": {
                "r_squared": result.r_squared,
                "observations": result.n_observations,
                "reliable": result.adjusted_r_squared > 0.3 and result.n_observations > 50,
            },
            "what_works": [
                {
                    "feature": f,
                    "coefficient": result.coefficients[f],
                    "p_value": result.p_values[f],
                    "confidence": "high" if result.p_values[f] < 0.01 else "moderate",
                }
                for f in result.top_positive_features
            ],
            "what_to_avoid": [
                {
                    "feature": f,
                    "coefficient": result.coefficients[f],
                    "p_value": result.p_values[f],
                    "confidence": "high" if result.p_values[f] < 0.01 else "moderate",
                }
                for f in result.top_negative_features
            ],
            "inconclusive": result.insignificant_features,
            "multicollinearity_warnings": [
                f for f, vif in result.vif_scores.items() if vif > 5
            ],
        }

        return playbook
