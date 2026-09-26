"""Load the sf_* BigQuery tables into a Salesforce org through the Bulk API.

Objects load parent-first so lookups resolve: Account, Campaign, Contact, Lead,
Opportunity, then CampaignMember. Every object except CampaignMember is *upserted* on a
GA4 external-id field, so re-running the load updates records instead of duplicating
them. Lookups are set by external id too (e.g. an Opportunity names its Contact by
GA4_User_Pseudo_Id__c), so no Salesforce record ids are needed.

Deploy the custom fields in salesforce/ before the first load (see the README).
"""

from __future__ import annotations

import datetime as dt
import decimal
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from uca.config import Settings


@dataclass(frozen=True)
class ObjectSpec:
    table: str
    sobject: str
    # Upsert key. None means insert (CampaignMember has no external-id field).
    external_id: str | None
    # Column holding an external id -> (relationship name, parent's external-id field).
    lookups: dict[str, tuple[str, str]] = field(default_factory=dict)


OBJECTS: tuple[ObjectSpec, ...] = (
    ObjectSpec("sf_accounts", "Account", "GA4_Account_Key__c"),
    ObjectSpec("sf_campaigns", "Campaign", "GA4_Campaign_Key__c"),
    ObjectSpec(
        "sf_contacts", "Contact", "GA4_User_Pseudo_Id__c",
        {"account_key": ("Account", "GA4_Account_Key__c")},
    ),
    ObjectSpec("sf_leads", "Lead", "GA4_User_Pseudo_Id__c"),
    ObjectSpec(
        "sf_opportunities", "Opportunity", "GA4_Transaction_Id__c",
        {
            "account_key": ("Account", "GA4_Account_Key__c"),
            "contact_key": ("GA4_Contact__r", "GA4_User_Pseudo_Id__c"),
            "campaign_key": ("Campaign", "GA4_Campaign_Key__c"),
        },
    ),
    ObjectSpec(
        "sf_campaign_members", "CampaignMember", None,
        {
            "campaign_key": ("Campaign", "GA4_Campaign_Key__c"),
            "contact_key": ("Contact", "GA4_User_Pseudo_Id__c"),
            "lead_key": ("Lead", "GA4_User_Pseudo_Id__c"),
        },
    ),
)

# Re-inserting an existing campaign member fails with this code; it is not an error here.
ALREADY_A_MEMBER = "DUPLICATE_VALUE"


def _value(v: Any) -> Any:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def to_records(spec: ObjectSpec, rows: Iterable[dict]) -> list[dict]:
    """Turn table rows into Bulk API records. NULLs are left out rather than sent."""
    records = []
    for row in rows:
        record = {}
        for column, value in row.items():
            if value is None:
                continue
            if column in spec.lookups:
                relationship, parent_key = spec.lookups[column]
                record[relationship] = {parent_key: _value(value)}
            else:
                record[column] = _value(value)
        records.append(record)
    return records


@dataclass
class LoadResult:
    sobject: str
    sent: int = 0
    succeeded: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.errors)

    def summary(self) -> str:
        text = f"{self.sobject}: {self.succeeded}/{self.sent} loaded"
        if self.skipped:
            text += f", {self.skipped} already present"
        if self.errors:
            text += f", {self.failed} failed (first: {self.errors[0]})"
        return text


def _error_text(result: dict) -> str:
    errors = result.get("errors") or []
    parts = []
    for e in errors:
        if isinstance(e, dict):
            parts.append(f"{e.get('statusCode')}: {e.get('message')}")
        else:
            parts.append(str(e))
    return "; ".join(parts) or "unknown error"


def send(sf, spec: ObjectSpec, records: list[dict], batch_size: int = 5000) -> LoadResult:
    """Upsert (or insert) records with simple-salesforce's Bulk API client."""
    result = LoadResult(spec.sobject, sent=len(records))
    if not records:
        return result
    handler = getattr(sf.bulk, spec.sobject)
    if spec.external_id:
        responses = handler.upsert(records, spec.external_id, batch_size=batch_size)
    else:
        responses = handler.insert(records, batch_size=batch_size)
    for response in responses:
        if response.get("success"):
            result.succeeded += 1
        elif ALREADY_A_MEMBER in _error_text(response):
            result.skipped += 1
        else:
            result.errors.append(_error_text(response))
    return result


def connect():
    """Log in with SF_USERNAME, SF_PASSWORD, SF_SECURITY_TOKEN and SF_DOMAIN."""
    from simple_salesforce import Salesforce

    missing = [v for v in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN") if not os.environ.get(v)]
    if missing:
        raise ValueError(f"Set {', '.join(missing)} (see .env.example)")
    return Salesforce(
        username=os.environ["SF_USERNAME"],
        password=os.environ["SF_PASSWORD"],
        security_token=os.environ["SF_SECURITY_TOKEN"],
        domain=os.environ.get("SF_DOMAIN", "login"),
    )


def load(
    sf,
    read_table: Callable[[str], Iterable[dict]],
    objects: tuple[ObjectSpec, ...] = OBJECTS,
    log=print,
) -> list[LoadResult]:
    """Load every object in order. Stops before children if a parent object had failures."""
    results = []
    for spec in objects:
        result = send(sf, spec, to_records(spec, read_table(spec.table)))
        log(result.summary())
        results.append(result)
        if result.errors:
            log(f"Stopping: fix the {spec.sobject} errors before loading records that depend on it.")
            break
    return results


def load_from_bigquery(settings: Settings, log=print) -> list[LoadResult]:
    """Read the sf_* tables built by `uca build salesforce` and load them into Salesforce."""
    from uca.runners import bigquery_client
    from uca.sql import table_ref

    client = bigquery_client(settings)

    def read_table(table: str) -> Iterable[dict]:
        rows = client.query(f"SELECT * FROM {table_ref(table, 'bigquery', settings)}").result()
        return [dict(row.items()) for row in rows]

    return load(connect(), read_table, log=log)
