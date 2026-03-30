"""
Creative Regression Model — decomposes ad performance into creative element coefficients.

This is the brain of the system. It answers: which creative elements actually drive
first-note completions, and which are noise?

Approach:
1. Encode each ad's MECE taxonomy into feature vectors (one-hot for categoricals)
2. Dependent variable: cost_per_first_note (lower = better)
3. Run OLS/WLS with VIF checks for multicollinearity
4. Output: ranked coefficients with significance levels

Features:
- Exponential decay weighting: recent ads count more than old ones
- Rolling window: separate model on just the last N days
- Interaction terms: boolean x categorical feature products

MECE is critical here. If taxonomy categories overlap, you get covariance problems
and the coefficients become uninterpretable. The taxonomy in models.py is designed
to be orthogonal across dimensions — but the intern should validate this empirically
with VIF scores on real data.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from engine.models import AdVariant, ExistingAd, PerformanceSnapshot, RegressionResult
from engine.store import Store

DEFAULT_HALF_LIFE_DAYS = 30


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
    "social_proof_type",
    "copy_length_bin",
]

# Numerical features used directly
NUMERICAL_FEATURES = [
    "headline_word_count",
    "copy_reading_level",
    "days_since_first_run",
]

# Boolean features (0/1)
BOOLEAN_FEATURES = [
    "uses_number",
    "uses_question",
    "uses_first_person",
    "uses_social_proof",
    "contains_specific_number",
    "shows_product_ui",
    "human_face_visible",
]


class CreativeRegressionModel:
    def __init__(self, store: Store):
        self.store = store

    def build_dataset(
        self,
        include_existing: bool = True,
        min_tag_confidence: float = 0.0,
    ) -> pd.DataFrame:
        """
        Build the regression dataset by joining variant taxonomy with performance data.
        Each row = one ad variant with aggregated performance metrics.
        When include_existing=True, also incorporates imported Meta/Google ads.

        min_tag_confidence: if > 0.0, filter out rows where any taxonomy field has
        tagging_confidence below this threshold. (A1) Default 0.0 = include all.

        Includes a 'last_activity_date' column for temporal decay weighting,
        and a 'days_since_first_run' column for fatigue modeling.
        """
        rows = []
        today = date.today()

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

            last_snapshot_date = max(s.date for s in snapshots)
            first_snapshot_date = min(s.date for s in snapshots)
            days_since_first_run = (today - first_snapshot_date).days

            tax = variant.taxonomy
            if min_tag_confidence > 0.0 and tax.tagging_confidence:
                if any(conf < min_tag_confidence for conf in tax.tagging_confidence.values()):
                    continue

            rows.append(self._taxonomy_row(
                variant_id=variant.id, cpa=cpa, conversion_rate=conversion_rate,
                ctr=ctr, total_spend=total_spend, total_first_notes=total_first_notes,
                tax=tax, last_activity_date=last_snapshot_date,
                days_since_first_run=days_since_first_run,
            ))

        # Imported existing ads (performance is pre-aggregated)
        if include_existing:
            for ad in self.store.get_existing_ads_with_taxonomy():
                # Filter out swipe files and any explicitly excluded ads (A4)
                if ad.exclude_from_regression:
                    continue
                if ad.spend < 20 or ad.impressions < 100:
                    continue

                cpa = ad.cost_per_conversion
                conversion_rate = ad.conversions / ad.clicks if ad.clicks > 0 else 0
                ctr = ad.ctr

                activity_date = ad.analyzed_at.date() if ad.analyzed_at else today
                days_since_first_run = (today - activity_date).days

                tax = ad.taxonomy
                if min_tag_confidence > 0.0 and tax.tagging_confidence:
                    if any(conf < min_tag_confidence for conf in tax.tagging_confidence.values()):
                        continue

                rows.append(self._taxonomy_row(
                    variant_id=ad.id, cpa=cpa, conversion_rate=conversion_rate,
                    ctr=ctr, total_spend=ad.spend, total_first_notes=ad.conversions,
                    tax=tax, last_activity_date=activity_date,
                    days_since_first_run=days_since_first_run,
                ))

        return pd.DataFrame(rows)

    @staticmethod
    def _taxonomy_row(
        variant_id: str, cpa, conversion_rate: float, ctr: float,
        total_spend: float, total_first_notes: int, tax,
        last_activity_date: Optional[date] = None,
        days_since_first_run: int = 0,
    ) -> dict:
        return {
            "variant_id": variant_id,
            "cost_per_first_note": cpa,
            "conversion_rate": conversion_rate,
            "ctr": ctr,
            "total_spend": total_spend,
            "total_first_notes": total_first_notes,
            "last_activity_date": last_activity_date or date.today(),
            "days_since_first_run": days_since_first_run,
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
            # Extended features (R2)
            "contains_specific_number": int(getattr(tax, "contains_specific_number", False)),
            "shows_product_ui": int(getattr(tax, "shows_product_ui", False)),
            "human_face_visible": int(getattr(tax, "human_face_visible", False)),
            "social_proof_type": getattr(tax, "social_proof_type", "none"),
            "copy_length_bin": getattr(tax, "copy_length_bin", "medium"),
            "asset_source": getattr(tax, "asset_source", "template"),
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

    def add_interaction_terms(
        self,
        X_encoded: pd.DataFrame,
        feature_names: list[str],
        y: np.ndarray,
        max_interactions: int = 20,
    ) -> tuple[pd.DataFrame, list[str]]:
        """
        Add pairwise interaction terms between boolean features and categorical dummies.
        
        - All 4 boolean features x all categorical dummy columns
        - Boolean x boolean pairs (6 combinations from 4 booleans)
        - Capped at max_interactions by correlation with target
        - Drops zero-variance and high-VIF (>10) interactions
        """
        interaction_candidates = []
        
        boolean_cols = [c for c in BOOLEAN_FEATURES if c in X_encoded.columns]
        categorical_dummy_cols = [
            c for c in X_encoded.columns
            if c not in BOOLEAN_FEATURES and c not in NUMERICAL_FEATURES
        ]
        
        for bool_col in boolean_cols:
            for cat_col in categorical_dummy_cols:
                interaction_name = f"{bool_col}_x_{cat_col}"
                interaction_vals = X_encoded[bool_col].values * X_encoded[cat_col].values
                
                if np.var(interaction_vals) > 0:
                    corr = np.abs(np.corrcoef(interaction_vals, y)[0, 1])
                    if not np.isnan(corr):
                        interaction_candidates.append({
                            "name": interaction_name,
                            "values": interaction_vals,
                            "corr": corr,
                        })
        
        for i, bool_a in enumerate(boolean_cols):
            for bool_b in boolean_cols[i + 1:]:
                interaction_name = f"{bool_a}_x_{bool_b}"
                interaction_vals = X_encoded[bool_a].values * X_encoded[bool_b].values
                
                if np.var(interaction_vals) > 0:
                    corr = np.abs(np.corrcoef(interaction_vals, y)[0, 1])
                    if not np.isnan(corr):
                        interaction_candidates.append({
                            "name": interaction_name,
                            "values": interaction_vals,
                            "corr": corr,
                        })
        
        interaction_candidates.sort(key=lambda x: -x["corr"])
        selected = interaction_candidates[:max_interactions]
        
        X_augmented = X_encoded.copy()
        augmented_names = list(feature_names)
        
        for item in selected:
            X_augmented[item["name"]] = item["values"]
            augmented_names.append(item["name"])
        
        return X_augmented, augmented_names

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

    def _compute_decay_weights(
        self, df: pd.DataFrame, half_life_days: int = DEFAULT_HALF_LIFE_DAYS
    ) -> np.ndarray:
        """
        Compute exponential decay weights based on observation age.
        w_i = exp(-lambda * days_since) where lambda = ln(2) / half_life
        """
        today = date.today()
        lambda_decay = np.log(2) / half_life_days
        
        days_since = np.array([
            (today - d).days if isinstance(d, date) else 0
            for d in df["last_activity_date"]
        ])
        
        weights = np.exp(-lambda_decay * days_since)
        weights = weights / weights.sum() * len(weights)
        
        return weights

    def run(
        self,
        target: str = "cost_per_first_note",
        min_observations: int = 10,
        use_weights: bool = True,
        half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
        window_days: Optional[int] = None,
        include_interactions: bool = True,
        max_interactions: int = 20,
    ) -> Optional[RegressionResult]:
        """
        Run the full regression analysis.

        target: which metric to model. Default is cost_per_first_note.
        Can also use "conversion_rate" or "ctr".
        use_weights: if True, apply exponential decay weighting (WLS).
        half_life_days: half-life for decay weighting (default 30).
        window_days: if set, filter to only observations within this many days.
        include_interactions: if True, add interaction terms.
        max_interactions: maximum number of interaction terms to include.
        """
        df = self.build_dataset()

        if len(df) < min_observations:
            print(f"Only {len(df)} observations — need at least {min_observations} for meaningful regression.")
            return None

        if window_days is not None:
            cutoff = date.today() - timedelta(days=window_days)
            df = df[df["last_activity_date"] >= cutoff]
            if len(df) < min_observations:
                print(f"Only {len(df)} observations in {window_days}-day window.")
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

        # Add interaction terms if requested
        if include_interactions and len(df) > max_interactions + len(feature_names):
            X_encoded, feature_names = self.add_interaction_terms(
                X_encoded, feature_names, y, max_interactions
            )

        # Add constant for intercept
        X = np.column_stack([np.ones(len(X_encoded)), X_encoded.values])
        all_names = ["intercept"] + feature_names

        # Compute sample weights if using WLS
        if use_weights and window_days is None:
            weights = self._compute_decay_weights(df, half_life_days)
            W = np.diag(np.sqrt(weights))
            X_w = W @ X
            y_w = W @ y
        else:
            weights = np.ones(len(y))
            X_w = X
            y_w = y

        # OLS/WLS regression
        try:
            beta = np.linalg.lstsq(X_w, y_w, rcond=None)[0]
        except np.linalg.LinAlgError:
            print("Regression failed — singular matrix. Check for perfect multicollinearity.")
            return None

        # Predictions and residuals (on original scale)
        y_hat = X @ beta
        residuals = y - y_hat
        n, k = X.shape

        # Weighted R-squared
        weighted_ss_res = np.sum(weights * residuals ** 2)
        weighted_mean_y = np.average(y, weights=weights)
        weighted_ss_tot = np.sum(weights * (y - weighted_mean_y) ** 2)
        r_squared = 1 - weighted_ss_res / weighted_ss_tot if weighted_ss_tot > 0 else 0
        adj_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - k - 1) if n > k + 1 else 0

        # Standard errors and p-values (for WLS)
        mse = weighted_ss_res / (n - k) if n > k else weighted_ss_res
        try:
            XtWX = X.T @ np.diag(weights) @ X
            var_beta = mse * np.linalg.inv(XtWX)
            se = np.sqrt(np.abs(np.diag(var_beta)))
        except np.linalg.LinAlgError:
            se = np.full(k, np.nan)

        t_stats = beta / se
        p_values = [2 * (1 - scipy_stats.t.cdf(abs(t), df=n - k)) for t in t_stats]

        t_crit = scipy_stats.t.ppf(0.975, df=n - k)

        # Build coefficient dict (skip intercept for reporting)
        # Sanitize NaN/inf → 0.0 for coefficients, 1.0 for p-values
        def _safe_float(v: float, default: float = 0.0) -> float:
            try:
                f = float(v)
                return default if (np.isnan(f) or np.isinf(f)) else f
            except (TypeError, ValueError):
                return default

        coefficients = {
            name: _safe_float(beta[i])
            for i, name in enumerate(all_names) if name != "intercept"
        }
        p_vals = {
            name: _safe_float(p_values[i], default=1.0)
            for i, name in enumerate(all_names) if name != "intercept"
        }

        # VIF scores — cap inf at 999.0, drop None
        raw_vif = self.calculate_vif(X_encoded)
        vif_scores = {
            k: min(_safe_float(v, default=999.0), 999.0)
            for k, v in raw_vif.items()
        }

        # Sanitize confidence intervals (NaN → 0.0)
        ci = {
            name: (
                _safe_float(beta[i] - t_crit * se[i]),
                _safe_float(beta[i] + t_crit * se[i]),
            )
            for i, name in enumerate(all_names)
        }

        # Durbin-Watson statistic
        diffs = np.diff(residuals)
        dw = float(np.sum(diffs ** 2) / weighted_ss_res) if weighted_ss_res > 0 else 0

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
            window_days=window_days,
            sample_weights_used=use_weights and window_days is None,
        )

    def run_with_validation(
        self,
        target: str = "cost_per_first_note",
        min_observations: int = 10,
        use_weights: bool = True,
        half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
        window_days: Optional[int] = None,
        include_interactions: bool = True,
        max_interactions: int = 20,
        n_bootstrap: int = 1000,
        n_stability_runs: int = 10,
        subsample_fraction: float = 0.8,
    ) -> Optional[RegressionResult]:
        """
        Run regression with full validation suite:
        - 80/20 train/test holdout (measures overfitting)
        - Bootstrap confidence intervals (1000 resamples, non-parametric)
        - Coefficient stability across 10 random 80% subsamples
        - Confidence tier assignment: high/moderate/directional/unreliable

        If test_r_squared < 0.15, the model is not learning real signal — coefficients
        should not be used for generation guidance (fall back to editorial memory).

        Tiering:
          high       = bootstrap CI doesn't cross 0 AND stability std < 0.3 * |coeff|
          moderate   = bootstrap CI doesn't cross 0
          directional = p < 0.10
          unreliable  = everything else
        """
        # Get the base result first
        base_result = self.run(
            target=target,
            min_observations=min_observations,
            use_weights=use_weights,
            half_life_days=half_life_days,
            window_days=window_days,
            include_interactions=include_interactions,
            max_interactions=max_interactions,
        )
        if base_result is None:
            return None

        # Build the full dataset for validation
        df = self.build_dataset()
        if window_days is not None:
            cutoff = date.today() - timedelta(days=window_days)
            df = df[df["last_activity_date"] >= cutoff]
        df = df.dropna(subset=[target])

        if len(df) < max(min_observations * 2, 20):
            # Not enough data for meaningful holdout — return base result with no validation
            return base_result

        n_total = len(df)
        feature_names_set = set(base_result.coefficients.keys())

        def _fit_subset(subset_df: pd.DataFrame) -> Optional[dict[str, float]]:
            """Fit regression on a subset DataFrame, return coefficients dict."""
            if len(subset_df) < min_observations:
                return None
            y_sub = subset_df[target].values
            X_sub, names_sub = self.encode_features(subset_df)
            non_zero = X_sub.columns[X_sub.var() > 0]
            X_sub = X_sub[non_zero]
            names_sub = list(non_zero)
            X_mat = np.column_stack([np.ones(len(X_sub)), X_sub.values])
            try:
                beta_sub = np.linalg.lstsq(X_mat, y_sub, rcond=None)[0]
            except np.linalg.LinAlgError:
                return None
            all_names_sub = ["intercept"] + names_sub
            return {n: float(beta_sub[i]) for i, n in enumerate(all_names_sub) if n != "intercept"}

        # --- Holdout validation (80/20 split) ---
        test_r_squared: Optional[float] = None
        try:
            from sklearn.model_selection import train_test_split
            train_idx, test_idx = train_test_split(
                range(n_total), test_size=0.2, random_state=42
            )
            train_df = df.iloc[train_idx].reset_index(drop=True)
            test_df = df.iloc[test_idx].reset_index(drop=True)

            train_coeffs = _fit_subset(train_df)
            if train_coeffs is not None and len(test_df) >= 5:
                # Encode test set with same feature names as train
                X_test_raw, test_names = self.encode_features(test_df)
                X_test_raw = X_test_raw.reindex(
                    columns=[c for c in base_result.coefficients.keys()
                             if c in X_test_raw.columns],
                    fill_value=0
                )
                X_test_mat = np.column_stack([np.ones(len(X_test_raw)), X_test_raw.values])
                beta_vec = np.array([
                    train_coeffs.get(n, 0.0) for n in X_test_raw.columns
                ])
                # Add intercept (not in coefficients dict)
                y_test = test_df[target].values
                # Simple prediction using only available features
                y_pred = X_test_raw.values @ beta_vec
                ss_res = np.sum((y_test - y_pred) ** 2)
                ss_tot = np.sum((y_test - np.mean(y_test)) ** 2)
                test_r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
                test_r_squared = round(max(-1.0, min(1.0, test_r_squared)), 4)
        except Exception as e:
            print(f"[regression] Holdout validation failed: {e}")

        # --- Bootstrap confidence intervals (1000 resamples) ---
        bootstrap_coeffs: dict[str, list[float]] = {f: [] for f in feature_names_set}
        for _ in range(n_bootstrap):
            boot_df = df.sample(n=n_total, replace=True, random_state=None)
            boot_df = boot_df.reset_index(drop=True)
            coeffs = _fit_subset(boot_df)
            if coeffs:
                for feat in feature_names_set:
                    if feat in coeffs:
                        bootstrap_coeffs[feat].append(coeffs[feat])

        bootstrap_ci: dict[str, tuple[float, float, float]] = {}
        for feat, vals in bootstrap_coeffs.items():
            if len(vals) >= 100:
                point = base_result.coefficients.get(feat, 0.0)
                lower = float(np.percentile(vals, 2.5))
                upper = float(np.percentile(vals, 97.5))
                bootstrap_ci[feat] = (round(point, 4), round(lower, 4), round(upper, 4))

        # --- Coefficient stability (10 subsample runs) ---
        stability_coeffs: dict[str, list[float]] = {f: [] for f in feature_names_set}
        n_subsample = int(n_total * subsample_fraction)
        for _ in range(n_stability_runs):
            sub_df = df.sample(n=n_subsample, replace=False, random_state=None)
            sub_df = sub_df.reset_index(drop=True)
            coeffs = _fit_subset(sub_df)
            if coeffs:
                for feat in feature_names_set:
                    if feat in coeffs:
                        stability_coeffs[feat].append(coeffs[feat])

        coefficient_stability: dict[str, float] = {}
        for feat, vals in stability_coeffs.items():
            if len(vals) >= 5:
                coefficient_stability[feat] = round(float(np.std(vals)), 4)

        # --- Confidence tiers ---
        confidence_tiers: dict[str, str] = {}
        for feat in feature_names_set:
            p_value = base_result.p_values.get(feat, 1.0)
            coeff = base_result.coefficients.get(feat, 0.0)
            ci_tuple = bootstrap_ci.get(feat)
            stability_std = coefficient_stability.get(feat)

            ci_crosses_zero = True
            if ci_tuple is not None:
                lower_ci, upper_ci = ci_tuple[1], ci_tuple[2]
                ci_crosses_zero = lower_ci <= 0 <= upper_ci

            is_stable = False
            if stability_std is not None and abs(coeff) > 0:
                is_stable = stability_std < 0.3 * abs(coeff)

            if not ci_crosses_zero and is_stable:
                confidence_tiers[feat] = "high"
            elif not ci_crosses_zero:
                confidence_tiers[feat] = "moderate"
            elif p_value < 0.10:
                confidence_tiers[feat] = "directional"
            else:
                confidence_tiers[feat] = "unreliable"

        # Return enriched result
        base_result.test_r_squared = test_r_squared
        base_result.bootstrap_ci = bootstrap_ci
        base_result.coefficient_stability = coefficient_stability
        base_result.confidence_tiers = confidence_tiers
        return base_result

    def run_rolling(
        self,
        window_days: int = 30,
        target: str = "cost_per_first_note",
        min_observations: int = 10,
        include_interactions: bool = True,
    ) -> Optional[RegressionResult]:
        """
        Run regression on only the last N days of data.
        Uses standard OLS (no decay weights) since we're already filtering by time.
        """
        return self.run(
            target=target,
            min_observations=min_observations,
            use_weights=False,
            window_days=window_days,
            include_interactions=include_interactions,
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

    def format_comparison(self, min_spend: float = 50.0) -> Optional[dict]:
        """
        Compare video vs static ad format performance.
        Returns group stats, delta percentage, t-test results, and regression
        coefficient for the format_video dummy if available.
        """
        df = self.build_dataset(include_existing=True)
        if df.empty:
            return None

        df = df[df["total_spend"] >= min_spend].copy()
        df = df.dropna(subset=["cost_per_first_note"])
        if len(df) < 4:
            return None

        video_formats = {"video", "reels", "story"}
        df["is_video"] = df["format"].isin(video_formats)

        static_df = df[~df["is_video"]]
        video_df = df[df["is_video"]]

        if len(static_df) < 2 or len(video_df) < 2:
            return None

        static_cpfn = static_df["cost_per_first_note"]
        video_cpfn = video_df["cost_per_first_note"]

        static_avg = float(static_cpfn.mean())
        video_avg = float(video_cpfn.mean())
        delta_pct = (static_avg - video_avg) / static_avg * 100 if static_avg else 0

        t_stat, p_val = scipy_stats.ttest_ind(
            static_cpfn.values, video_cpfn.values, equal_var=False,
        )

        # Extract regression coefficient for format_video if available
        reg_coef = None
        reg_p = None
        latest = self.store.get_latest_regression()
        if latest:
            for key in latest.coefficients:
                if "format" in key.lower() and "video" in key.lower():
                    reg_coef = latest.coefficients[key]
                    reg_p = latest.p_values.get(key)
                    break

        return {
            "static": {
                "avg_cpfn": round(static_avg, 2),
                "median_cpfn": round(float(static_cpfn.median()), 2),
                "count": int(len(static_df)),
                "total_spend": round(float(static_df["total_spend"].sum()), 2),
            },
            "video": {
                "avg_cpfn": round(video_avg, 2),
                "median_cpfn": round(float(video_cpfn.median()), 2),
                "count": int(len(video_df)),
                "total_spend": round(float(video_df["total_spend"].sum()), 2),
            },
            "delta_pct": round(delta_pct, 1),
            "video_is_better": video_avg < static_avg,
            "t_statistic": round(float(t_stat), 3),
            "p_value": round(float(p_val), 4),
            "significant": float(p_val) < 0.05,
            "regression_coefficient": round(reg_coef, 4) if reg_coef is not None else None,
            "regression_p_value": round(reg_p, 4) if reg_p is not None else None,
            "sample_sizes": {
                "static": int(len(static_df)),
                "video": int(len(video_df)),
            },
        }
