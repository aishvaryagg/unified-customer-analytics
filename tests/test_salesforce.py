"""Salesforce models, metadata consistency and the loader (no org needed)."""

import hashlib
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from conftest import query
from uca.salesforce import OBJECTS, LoadResult, load, send, to_records

METADATA = Path(__file__).resolve().parents[1] / "salesforce" / "force-app" / "main" / "default"
NS = {"md": "http://soap.sforce.com/2006/04/metadata"}

# Standard fields the sf_* tables are allowed to set.
STANDARD_FIELDS = {
    "Account": {"Name", "Type", "Industry"},
    "Campaign": {"Name", "Type", "Status", "IsActive", "StartDate", "EndDate"},
    "Contact": {"LastName", "LeadSource"},
    "Lead": {"LastName", "Company", "LeadSource", "Status"},
    "Opportunity": {"Name", "StageName", "CloseDate", "Amount"},
    "CampaignMember": {"Status"},
}


def custom_fields():
    """{object: {field name: parsed XML root}} from the deployable metadata."""
    fields = {}
    for path in METADATA.glob("objects/*/fields/*.field-meta.xml"):
        root = ET.parse(path).getroot()
        name = root.findtext("md:fullName", namespaces=NS)
        assert path.name == f"{name}.field-meta.xml"
        fields.setdefault(path.parent.parent.name, {})[name] = root
    return fields


def by(rows, key):
    return {r[key]: r for r in rows}


# --- models ---------------------------------------------------------------------------

def md5(text):
    return hashlib.md5(text.encode()).hexdigest()


def test_people_classified_and_sampled_by_hash(sf):
    p = by(query(sf, "SELECT * FROM int_sf__people"), "user_pseudo_id")
    assert {u: r["crm_type"] for u, r in p.items()} == {
        "u1": "Contact", "u2": "Contact", "u4": "Contact", "u5": "Lead", "u6": "Lead",
    }
    assert p["u5"]["highest_funnel_stage"] == "Add to cart"
    assert p["u6"]["highest_funnel_stage"] == "Checkout"
    expected_contacts = set(sorted(["u1", "u2", "u4"], key=md5)[:2])
    assert {u for u, r in p.items() if r["crm_type"] == "Contact" and r["in_sample"]} == expected_contacts
    expected_lead = sorted(["u5", "u6"], key=md5)[0]
    assert {u for u, r in p.items() if r["crm_type"] == "Lead" and r["in_sample"]} == {expected_lead}


def test_only_sampled_people_and_their_records_are_exported(sf):
    sampled = {r["user_pseudo_id"] for r in query(sf, "SELECT * FROM int_sf__people WHERE in_sample")}
    contacts = {r["GA4_User_Pseudo_Id__c"] for r in query(sf, "SELECT * FROM sf_contacts")}
    leads = {r["GA4_User_Pseudo_Id__c"] for r in query(sf, "SELECT * FROM sf_leads")}
    assert len(contacts) == 2 and len(leads) == 1 and contacts | leads == sampled
    opp_owners = {r["contact_key"] for r in query(sf, "SELECT * FROM sf_opportunities")}
    assert opp_owners == contacts
    members = query(sf, "SELECT * FROM sf_campaign_members")
    assert {m["contact_key"] or m["lead_key"] for m in members} == sampled
    assert all((m["contact_key"] is None) != (m["lead_key"] is None) for m in members)


def test_campaigns_use_all_sessions_not_the_sample(sf):
    c = by(query(sf, "SELECT * FROM sf_campaigns"), "GA4_Campaign_Key__c")
    paid = c["Paid Search|winter_sale"]
    assert paid["GA4_Sessions__c"] == 3  # u2's two sessions + u5's, whoever is sampled
    assert paid["GA4_Users__c"] == 2
    assert paid["GA4_Revenue__c"] == 30
    assert paid["GA4_Conversion_Rate__c"] == pytest.approx(33.33)
    assert paid["Type"] == "Advertisement" and paid["Status"] == "Completed"
    assert paid["StartDate"] == date(2020, 11, 3) and paid["EndDate"] == date(2020, 12, 10)
    assert c["Email|nov_newsletter"]["Type"] == "Email"
    assert all(len(r["Name"]) <= 80 for r in c.values())


def test_contacts_profile_and_next_best_category(sf_full):
    c = by(query(sf_full, "SELECT * FROM sf_contacts"), "GA4_User_Pseudo_Id__c")
    assert set(c) == {"u1", "u2", "u4"}
    u1 = c["u1"]
    assert u1["LastName"] == f"GA4 Customer {md5('u1')[:8]}"
    assert u1["Lifetime_Revenue__c"] == 95 and u1["GA4_Transactions__c"] == 3
    assert u1["Revenue_Trend__c"] == "Contraction"
    assert u1["Acquisition_Channel__c"] == "Organic Search"
    assert u1["Is_Churned__c"] is False and u1["Is_Lapsed_Purchaser__c"] is True
    assert u1["Last_Purchase_Date__c"] == date(2020, 11, 17)
    # Last purchase was Bags; Organic Search customers moved from Bags to Drinkware.
    assert (u1["Next_Best_Category__c"], u1["Next_Best_Category_Probability__c"]) == ("Drinkware", 100)
    assert c["u4"]["Next_Best_Category__c"] == "Bags"
    # u2 (Direct) has no segment data, so the all-customers pattern is used; Bags is
    # skipped because u2's last order already contained it.
    assert c["u2"]["Next_Best_Category__c"] == "Drinkware"
    assert c["u2"]["Revenue_Trend__c"] == "Insufficient history"


def test_opportunities(sf_full):
    o = by(query(sf_full, "SELECT * FROM sf_opportunities"), "GA4_Transaction_Id__c")
    assert set(o) == {"t1", "t2", "t3", "t4", "t5", "t6"}  # t4's duplicate event is not an extra order
    t2 = o["t2"]
    assert t2["StageName"] == "Closed Won" and t2["Amount"] == 45
    assert t2["CloseDate"] == date(2020, 11, 10)
    assert t2["campaign_key"] == "Email|nov_newsletter"
    assert (t2["First_Touch_Channel__c"], t2["Last_Touch_Channel__c"]) == ("Organic Search", "Email")
    assert sum(r["Amount"] for r in o.values()) == 175


def test_campaign_member_status(sf):
    m = query(sf, "SELECT * FROM sf_campaign_members")
    lead_rows = [r for r in m if r["lead_key"]]
    [lead] = lead_rows
    # Both leads added to cart in their only campaign.
    assert lead["Status"] == "Responded"


def test_leads(sf):
    [lead] = query(sf, "SELECT * FROM sf_leads")
    assert lead["Company"] == "Individual" and lead["Status"] == "Open - Not Contacted"
    assert lead["Highest_Funnel_Stage__c"] in ("Add to cart", "Checkout")


# --- metadata -------------------------------------------------------------------------

def test_every_exported_column_is_a_real_field(sf):
    fields = custom_fields()
    for spec in OBJECTS:
        columns = [d[0] for d in sf.execute(f"SELECT * FROM {spec.table} LIMIT 0").description]
        for column in columns:
            if column in spec.lookups:
                continue
            if column.endswith("__c"):
                assert column in fields.get(spec.sobject, {}), f"{spec.sobject}.{column} has no metadata"
            else:
                assert column in STANDARD_FIELDS[spec.sobject], f"{spec.sobject}.{column} is not allowed"


def test_upsert_keys_are_unique_external_ids():
    fields = custom_fields()
    for spec in OBJECTS:
        if spec.external_id:
            root = fields[spec.sobject][spec.external_id]
            assert root.findtext("md:externalId", namespaces=NS) == "true"
            assert root.findtext("md:unique", namespaces=NS) == "true"
        for relationship, parent_key in spec.lookups.values():
            parent = relationship.removesuffix("__r")
            if relationship.endswith("__r"):
                lookup = fields[spec.sobject][f"{parent}__c"]
                parent = lookup.findtext("md:referenceTo", namespaces=NS)
            assert fields[parent][parent_key].findtext("md:externalId", namespaces=NS) == "true"


def test_permission_set_covers_every_custom_field():
    root = ET.parse(METADATA / "permissionsets" / "GA4_Marketing_Analytics.permissionset-meta.xml").getroot()
    granted = {fp.findtext("md:field", namespaces=NS) for fp in root.findall("md:fieldPermissions", NS)}
    defined = {f"{obj}.{name}" for obj, names in custom_fields().items() for name in names}
    assert granted == defined


# --- loader ---------------------------------------------------------------------------

class FakeHandler:
    def __init__(self, log, sobject, responses=None):
        self.log, self.sobject, self.responses = log, sobject, responses

    def _respond(self, records):
        return self.responses or [{"success": True, "errors": []} for _ in records]

    def upsert(self, records, external_id, batch_size):
        self.log.append(("upsert", self.sobject, external_id, records))
        return self._respond(records)

    def insert(self, records, batch_size):
        self.log.append(("insert", self.sobject, None, records))
        return self._respond(records)


class FakeSalesforce:
    def __init__(self, responses=None):
        self.log, self.responses = [], responses or {}
        outer = self

        class Bulk:
            def __getattr__(self, sobject):
                return FakeHandler(outer.log, sobject, outer.responses.get(sobject))

        self.bulk = Bulk()


def test_to_records_builds_external_id_lookups_and_drops_nulls():
    spec = next(s for s in OBJECTS if s.sobject == "CampaignMember")
    [record] = to_records(spec, [{"campaign_key": "Email|x", "contact_key": None, "lead_key": "u5",
                                  "Status": "Sent"}])
    assert record == {
        "Campaign": {"GA4_Campaign_Key__c": "Email|x"},
        "Lead": {"GA4_User_Pseudo_Id__c": "u5"},
        "Status": "Sent",
    }
    opp = next(s for s in OBJECTS if s.sobject == "Opportunity")
    [record] = to_records(opp, [{"contact_key": "u1", "CloseDate": date(2020, 11, 10)}])
    assert record == {"GA4_Contact__r": {"GA4_User_Pseudo_Id__c": "u1"}, "CloseDate": "2020-11-10"}


def test_load_sends_parents_first_and_upserts_on_external_ids(sf):
    fake = FakeSalesforce()
    results = load(fake, lambda table: query(sf, f"SELECT * FROM {table}"), log=lambda _: None)
    assert [call[1] for call in fake.log] == [
        "Account", "Campaign", "Contact", "Lead", "Opportunity", "CampaignMember"]
    assert [call[0] for call in fake.log] == ["upsert"] * 5 + ["insert"]
    assert fake.log[2][2] == "GA4_User_Pseudo_Id__c"
    assert all(r.failed == 0 for r in results)
    opportunities = len(query(sf, "SELECT * FROM sf_opportunities"))
    assert [r.sent for r in results if r.sobject == "Opportunity"] == [opportunities]


def test_existing_campaign_members_are_skipped_not_failed():
    spec = next(s for s in OBJECTS if s.sobject == "CampaignMember")
    fake = FakeSalesforce({"CampaignMember": [
        {"success": True, "errors": []},
        {"success": False, "errors": [{"statusCode": "DUPLICATE_VALUE", "message": "Already a campaign member."}]},
    ]})
    result = send(fake, spec, [{"Status": "Sent"}, {"Status": "Sent"}])
    assert (result.succeeded, result.skipped, result.failed) == (1, 1, 0)


def test_load_stops_before_children_when_a_parent_fails():
    fake = FakeSalesforce({"Account": [
        {"success": False, "errors": [{"statusCode": "INVALID_FIELD", "message": "No such column"}]}]})
    results = load(fake, lambda table: [{"GA4_Account_Key__c": "k"}], log=lambda _: None)
    assert [r.sobject for r in results] == ["Account"]
    assert isinstance(results[0], LoadResult) and "INVALID_FIELD" in results[0].errors[0]
