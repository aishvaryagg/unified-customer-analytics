# Salesforce

GA4 behaviour is pushed into Salesforce so marketing results sit next to CRM records:
campaigns carry their GA4 performance, customers carry their segment and churn risk, and
every order is an Opportunity credited to the campaign that closed it.

## Setup

One-time, in a free [Salesforce Developer Edition](https://developer.salesforce.com/signup) org.

1. Install the [Salesforce CLI](https://developer.salesforce.com/tools/salesforcecli) and log in:
   ```bash
   sf org login web --alias ga4-dev
   ```
2. Deploy the custom fields and permission set from `salesforce/`:
   ```bash
   cd salesforce
   sf project deploy start --source-dir force-app --target-org ga4-dev
   sf org assign permset --name GA4_Marketing_Analytics --target-org ga4-dev
   ```
   The permission set gives your user access to the new fields. Without it they exist but
   stay hidden and the load cannot write to them.
3. Get your security token: in Salesforce, **Settings → My Personal Information → Reset My
   Security Token**. It is emailed to you.
4. Fill in `SF_USERNAME`, `SF_PASSWORD`, `SF_SECURITY_TOKEN` and `SF_DOMAIN` in `.env`.

Then build and load:

```bash
uca build ga4          # if not already built
uca build salesforce   # sf_* tables in BigQuery
uca sf-load
```

`uca sf-load` upserts on the GA4 external-id fields, so running it again updates records
instead of creating duplicates. It stops before loading child objects if a parent object
had errors, and prints the first error for each object.

## How GA4 maps to Salesforce

| Object | Records | Upsert key | Notes |
|---|---|---|---|
| Account | 1 | `GA4_Account_Key__c` | One house account for all online customers (B2C without Person Accounts) |
| Campaign | one per GA4 channel + campaign | `GA4_Campaign_Key__c` (`channel\|campaign`) | Performance fields use **all** GA4 sessions |
| Contact | sampled purchasers | `GA4_User_Pseudo_Id__c` | Under the house account |
| Lead | sampled non-purchasers who added to cart or started checkout | `GA4_User_Pseudo_Id__c` | `Company = 'Individual'`, status `Open - Not Contacted` |
| Opportunity | every order of a sampled contact | `GA4_Transaction_Id__c` | `Closed Won`, `Amount` = order revenue (USD), `CloseDate` = order date |
| CampaignMember | each sampled person × campaign they arrived through | inserted | `Responded` if they added to cart or bought in that campaign's sessions, else `Sent` |

**Attribution.** Each Opportunity's Primary Campaign Source is the **last-touch** campaign
(the session the order was placed in), so Salesforce's standard campaign reports show
last-touch revenue. `First_Touch_Channel__c` and `Last_Touch_Channel__c` are stored too.
The first-touch and linear comparison lives in the `mart_attribution` model.

**Sampling.** A Developer Edition org has about 5 MB of data storage, roughly 2,500
records at 2 KB each. The default sample (400 contacts, 200 leads, their ~500 orders and
~700 campaign memberships, plus ~20 campaigns) is about 1,800 records. People are chosen
by an MD5 hash of their GA4 id: pseudo-random but repeatable, so every rebuild sends the
same people. Change `SF_MAX_CONTACTS` / `SF_MAX_LEADS` for a larger org. Campaign
figures are not affected by sampling.

**Privacy.** GA4 records are anonymous. Contacts and Leads are named `GA4 Customer
<hash>` / `GA4 Visitor <hash>`; no names, emails or other personal data are invented.

## Custom fields

All fields are in `salesforce/force-app/main/default/objects/`.

| Object | Field | Type | Meaning |
|---|---|---|---|
| Account | GA4_Account_Key__c | Text, external id | Key of the house account |
| Campaign | GA4_Campaign_Key__c | Text, external id | `channel\|campaign` |
| Campaign | Channel_Group__c, GA4_Campaign_Name__c | Text | GA4 channel group and campaign name |
| Campaign | GA4_Sessions__c, GA4_Users__c, GA4_Transactions__c | Number | Across all GA4 data |
| Campaign | GA4_Revenue__c | Currency | Last-touch revenue (USD) |
| Campaign | GA4_Conversion_Rate__c | Percent | Sessions with a purchase ÷ sessions |
| Contact, Lead | GA4_User_Pseudo_Id__c | Text, external id | GA4's anonymous user id |
| Contact, Lead | Acquisition_Channel__c | Text | First-touch channel |
| Contact, Lead | First_Seen_Date__c, Last_Seen_Date__c | Date | Activity window |
| Contact, Lead | GA4_Sessions__c | Number | Sessions |
| Contact, Lead | Is_Churned__c | Checkbox | No activity in the last `CHURN_DAYS` days |
| Contact | Last_Purchase_Date__c | Date | Most recent order |
| Contact | GA4_Transactions__c, Lifetime_Revenue__c | Number, Currency | Orders and revenue |
| Contact | Recency_Score__c, Frequency_Score__c, Monetary_Score__c | Number (1–5) | RFM scores |
| Contact | RFM_Segment__c | Text | Champion, Recent customer, At-risk high value, Lapsing customer |
| Contact | Revenue_Trend__c | Text | Latest Expansion / Contraction / Flat label |
| Contact | Is_Lapsed_Purchaser__c | Checkbox | Bought before, not in the last `CHURN_DAYS` days |
| Contact | Next_Best_Category__c, Next_Best_Category_Probability__c | Text, Percent | Cross-sell recommendation from the last order |
| Lead | Highest_Funnel_Stage__c | Text | `Add to cart` or `Checkout` |
| Opportunity | GA4_Transaction_Id__c | Text, external id | GA4 transaction id |
| Opportunity | GA4_Contact__c | Lookup(Contact) | Customer who placed the order |
| Opportunity | First_Touch_Channel__c, Last_Touch_Channel__c | Text | Attribution channels |
| Opportunity | GA4_Item_Quantity__c | Number | Items in the order |

**Next best category.** From the customer's most recent order, the category customers
most often bought next (`mart_next_category`): for the customer's acquisition channel if
that segment has data, otherwise across all customers. Categories already in that order
are skipped.

## Reports to build in Salesforce

Once loaded, these standard report types answer marketing questions without extra code:

- **Campaigns with Opportunities:** revenue and orders by campaign (last touch).
- **Campaigns:** GA4 sessions, conversion rate and revenue side by side for every campaign.
- **Contacts & Accounts,** grouped by `RFM_Segment__c`, filtered on `Is_Lapsed_Purchaser__c`:
  the win-back list.
- **Contacts & Accounts,** grouped by `Next_Best_Category__c`: cross-sell campaign audiences.
- **Leads,** grouped by `Highest_Funnel_Stage__c` and `Acquisition_Channel__c`: which
  channels bring shoppers who abandon at checkout.
- **Campaigns with Leads and Contacts:** response (Responded vs Sent) by campaign.

## Testing

The tests build the Salesforce tables from the GA4 fixture and check the sampling, the
next-best-category logic and every exported value. They also check that every column the
loader sends is either a defined custom field or an allowed standard field, that every
upsert key and lookup points at a unique external-id field, and that the permission set
covers every custom field. The loader is tested against a fake Salesforce client. Nothing
here has been deployed to a real org yet.
