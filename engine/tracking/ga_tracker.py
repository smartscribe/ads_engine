"""
Google Analytics 4 Tracker — pulls landing page / traffic source performance
via the GA4 Data API.

Authenticates with a service account key whose email has been granted Viewer
on the target GA property. See docs/ga4-csp-fix-2026-04-13.md for the property
mapping and the history of why this integration exists.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd


class GAClient:
    """Thin wrapper around BetaAnalyticsDataClient for landing-page reports."""

    def __init__(self, property_id: str, credentials_path: str):
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
        self._client = BetaAnalyticsDataClient(credentials=creds)
        self._property = f"properties/{property_id}"

    def pull_landing_pages(
        self,
        start_date: date,
        end_date: date,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Landing-page performance grouped by landing page + source/medium.

        Returns a DataFrame with one row per (landing_page, source_medium) pair.
        """
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            OrderBy,
            RunReportRequest,
        )

        request = RunReportRequest(
            property=self._property,
            date_ranges=[DateRange(start_date=start_date.isoformat(), end_date=end_date.isoformat())],
            dimensions=[
                Dimension(name="landingPagePlusQueryString"),
                Dimension(name="sessionSourceMedium"),
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="engagedSessions"),
                Metric(name="engagementRate"),
                Metric(name="totalUsers"),
                Metric(name="newUsers"),
                Metric(name="conversions"),
                Metric(name="averageSessionDuration"),
            ],
            order_bys=[
                OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
            ],
            limit=limit,
        )

        response = self._client.run_report(request)
        return self._response_to_frame(response, start_date, end_date)

    def pull_daily_traffic(
        self,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Daily sessions + users by source/medium — for time-series trend views."""
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            OrderBy,
            RunReportRequest,
        )

        request = RunReportRequest(
            property=self._property,
            date_ranges=[DateRange(start_date=start_date.isoformat(), end_date=end_date.isoformat())],
            dimensions=[
                Dimension(name="date"),
                Dimension(name="sessionSourceMedium"),
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="totalUsers"),
                Metric(name="newUsers"),
                Metric(name="conversions"),
            ],
            order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
            limit=10000,
        )

        response = self._client.run_report(request)
        return self._response_to_frame(response, start_date, end_date)

    @staticmethod
    def _response_to_frame(response, start_date: date, end_date: date) -> pd.DataFrame:
        dim_names = [d.name for d in response.dimension_headers]
        met_names = [m.name for m in response.metric_headers]

        rows = []
        for row in response.rows:
            record = {}
            for name, value in zip(dim_names, row.dimension_values):
                record[name] = value.value
            for name, value in zip(met_names, row.metric_values):
                try:
                    record[name] = float(value.value)
                except ValueError:
                    record[name] = value.value
            rows.append(record)

        df = pd.DataFrame(rows)
        df.attrs["start_date"] = start_date.isoformat()
        df.attrs["end_date"] = end_date.isoformat()
        return df


def load_client_from_settings() -> Optional[GAClient]:
    """
    Convenience: build a GAClient from project settings, or return None if
    credentials file is missing. Call sites can use this to degrade gracefully
    when auth isn't configured yet.
    """
    from pathlib import Path

    from config.settings import get_settings

    settings = get_settings()
    if not Path(settings.GA_CREDENTIALS_PATH).exists():
        return None
    return GAClient(
        property_id=settings.GA_PROPERTY_ID,
        credentials_path=settings.GA_CREDENTIALS_PATH,
    )
