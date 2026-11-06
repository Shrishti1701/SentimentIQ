# SentimentIQ Data Source Research

**Research checked:** 4 November 2026  
**Scope:** Indian listed-company announcements and financial news for an aspect-based sentiment MVP. This is source research only; it does not authorize collection, storage, model training, or redistribution. Do not infer API endpoints from a website's internal network calls.

## How to read this report

- **Verified** means the provider publishes the fact in the linked official material.
- **Needs confirmation** means public documentation does not settle the point, or a contract, account, trial, or provider response is needed.
- Fees below are quoted only where an official tariff page publishes them. They can change and should be reconfirmed before budgeting.
- “Real-time” describes provider product wording, not a guaranteed end-to-end delivery SLA. A feed can have provider, network, and processing delays.

## Executive comparison

| Source | Public machine interface verified? | Freshness / history | Authentication and published limits | MVP assessment |
|---|---|---|---|---|
| NSE announcements RSS | Official RSS directory exists; exact feed URL/schema and reuse terms are not documented on the directory page | Described as a real-time listing, subject to feed-reader/provider delays; backfill depth not specified | No auth or numeric polling limit stated | Best low-cost first experiment, subject to written reuse/polling clarification |
| NSE licensed corporate data | Yes: multicast real-time feed and SFTP end-of-day product are documented | Realtime CA packets; EOD daily file; historical backfill depth unclear | Subscription/agreement; paid; no request-per-minute quota stated | Most authoritative and technically specified; high setup/cost for an MVP |
| BSE announcements / corporate data | Public announcement page exists; paid corporate-data API/feed is advertised, but public technical endpoint/schema is not documented | Real-time/intraday and historical corporate data products advertised; precise announcement coverage/backfill needs confirmation | Registration, KYC, plan, agreement and payment for data feed; no public API rate limit | Credible official source, but onboarding and contract details precede implementation |
| Upstox News API | Documented REST endpoint for news keyed to Upstox instruments/holdings/positions | Articles published in the preceding 7 days; no delivery SLA stated | OAuth 2.0 user access token; general API limits published, endpoint mapping should be confirmed | Useful supplemental feed for selected NSE instruments, not an exchange-wide news archive |
| NewsAPI.org | Documented REST endpoints | Developer tier has 24-hour delay and one-month lookback; paid tiers advertise real-time and up to five years | API key; developer quota 100/day | Convenient prototype only; unsuitable for live/commercial MVP on free tier |
| TheNewsAPI.com | Documented REST endpoints | Pricing page advertises real-time and historical data; exact lookback depth is not stated on the public plan page | API token in query parameter; daily plan quotas; 429 behavior documented | Candidate for a small news-source trial after rights and India-source coverage are checked |

## 1. NSE corporate announcements

### 1.1 Public RSS directory

**Provider:** National Stock Exchange of India (NSE)  
**Official documentation:** [NSE RSS Feeds](https://www.nseindia.com/static/rss-feed)  
**Related announcements page:** [Corporate Filings — Announcements](https://www.nseindia.com/companies-listing/corporate-filings-announcements)

**Verified facts**

- NSE lists an RSS feed category for Corporate Information, including **Announcements**, as well as results, board meetings, shareholding, corporate actions, and other filing categories.
- NSE describes the feed as providing a real-time listing of current corporate information, press releases, circulars, and reports. NSE also warns that feed-reader/service-provider delays may occur and are outside NSE's control.
- The public announcements page visibly offers company/symbol and keyword search, date ranges including custom dates, a CSV download control, attachment links, and broadcast date/time. Its displayed announcement detail also includes exchange received time, dissemination time, and elapsed time for some records.

**Access method:** Official RSS subscription for announcements, plus browser-based search/download on the announcements page. The RSS directory links to feed icons, but the published page does not provide a stable textual endpoint list or a formal feed schema. This research therefore does not reproduce or guess an RSS URL.  
**Authentication:** The RSS instructions describe subscribing through a feed reader; they do not specify API credentials. Whether automated server-side consumption requires additional registration is **needs confirmation**.  
**Available data:** The directory promises a summary of new/changed items, not full-text article or attachment content. Company, subject, details, attachment, and timing fields are shown on the exchange announcement page, but their presence in RSS items is **not verified**.  
**Timestamps/history:** Page results show broadcast time and, for some entries, exchange-received and exchange-dissemination timestamps. The RSS retention/backfill window, update cadence, and timestamp field names are **not documented**. The page's filters and CSV control provide a user-facing history interface; automated historical export/API access is **not verified**.  
**Rate limits/polling:** No numeric request limit or recommended interval appears on the RSS page. The word “real-time” is not a polling SLA. A conservative polling interval is an engineering proposal only, not an NSE-approved interval; ask NSE before operating a persistent collector.  
**Licensing:** The RSS page does not state whether an application may store announcement summaries or attachments, run NLP/model training on them, or expose derived insights commercially. The separate NSE Data policy governs market-data products and subscriptions, but public materials do not make clear whether/how each RSS field is covered. Obtain written clarification before retaining or redistributing feed content.  
**Integration complexity:** Low-to-medium for a feed reader after the actual feed URL and schema are confirmed; medium for reliable ingestion because of unknown item identity, attachment linking, update semantics, deduplication, and history. Browser automation or undocumented site calls would be fragile and are not recommended.

**Suitability for SentimentIQ:** Best first feasibility test because an official RSS option is openly advertised and can focus on company disclosures. It is not yet a production-ready ingestion authorization: the URL/schema, automated polling terms, retention/model use rights, and attachment access remain to be established.

### 1.2 Licensed NSE corporate-data feeds

**Provider:** NSE Data & Analytics Limited (NSE Data)  
**Official product pages:** [Paid Corporate Data](https://www.nseindia.com/static/market-data/corporate-data-subscription), [Data Sharing & Usage Policy](https://www.nseindia.com/static/market-data/nse-data-policy)  
**Official technical documents:** [Corporate Data multicast specification, v2.4 (19 Dec 2024)](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Download_Technical_Specification_Corporate_Data.pdf), [Corporate Data EOD specification, v1.2 (23 Jan 2025)](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/EOD_DATA-Corporate_EODv1.2.pdf)

**Verified facts**

- The paid corporate-data page describes company fundamentals, announcements, and shareholding pattern. The real-time product is delivered on a dedicated leased line from an NSE point of presence to the subscriber premises. The page lists annual fees of **₹1,060,000 domestic** or **US$17,500 international** for Corporate Data.
- The page lists an **End-of-Day Corporate Announcement** product over internet/SFTP at **₹500,000 domestic** or **US$8,000 international per year**. The page says it is available after 20:00 IST daily; the technical specification gives a more precise file availability window of **22:40–23:45 IST** on the active servers, then a backup path after 23:45. Confirm the current operating window with NSE Data.
- The multicast specification says corporate announcements are sent when published (the real-time feed operates 02:00–22:30 IST). The feed uses compressed, sequenced multicast packets; LZO decompression is specified. Announcement records include security symbol, short description, details, announcement date/time (`DDMMYYYYHHmm`), and attachment filename; the attachment is available over SFTP. Sequence numbers reset daily, and heartbeat signals are part of the feed, supporting gap/continuity monitoring.
- The EOD specification describes daily CSV files, with a trigger file indicating data availability. Its announcement fields include symbol, description, details, announcement date/time, and attachment filename. The EOD product also contains company results and shareholding-distribution data. The tech document says credentials and paths are issued after commercial terms are completed.
- NSE's data policy requires subscribers to communicate requirements and execute a relevant agreement covering intended use and handling/distribution. Commercial access is priced; redistribution is not allowed except as the agreement permits. Data ownership remains with NSE/NSE Data.

**Access method:** Commercial subscription. Realtime: dedicated leased line and multicast packet receiver. EOD: internet SFTP files and trigger-file workflow.  
**Authentication:** Subscription/account agreement; EOD credentials and paths are provided after commercial completion. Specific credential provisioning, IP controls, and current network requirements should be confirmed during onboarding. The multicast technical spec revision notes that earlier login-request/login-response packets were removed; do not assume a login protocol from older integrations.  
**Available data:** Announcement metadata and attachment names, plus company results, segment results, and shareholding data depending on product. Attachment documents are separate; content extraction/OCR and their permitted retention require separate validation.  
**Timestamps/history:** Announcement timestamp is documented to minute precision. EOD includes daily announcements; official sources reviewed here do not specify a guaranteed historical backfill depth for this product. Ask whether historic files and corrections/revisions are included and how far back.  
**Rate limits/polling:** A persistent multicast feed is event-driven; the EOD spec instructs clients to wait for the trigger file before downloading. No HTTP-style calls-per-minute limit is published. Confirm SFTP concurrency, retry behavior, retention windows, and permitted connection frequency in the subscriber agreement.  
**Licensing:** Explicit contract required. The data-sharing policy places end-user, redistribution, and use restrictions in that contract, and pricing is separate. The technical specifications themselves carry copyright notices restricting reproduction/distribution without permission. Confirm whether internal NLP, model training, storage of source text/attachments, serving derived sentiment, and customer display are all covered.  
**Integration complexity:** High for real-time (leased line, binary packet framing, sequence handling, LZO, heartbeat/recovery, SFTP attachments); medium for EOD (SFTP, scheduled trigger detection, gzip/CSV parsing, attachment retrieval, and missing/revised-file handling).

**Suitability for SentimentIQ:** Strongest official machine-readable option and the best future production-grade NSE source if its terms and budget fit. The EOD product can support a once-daily prototype but is not intraday real-time. The realtime product is technically capable but likely disproportionate for the first MVP.

## 2. BSE corporate announcements

**Provider:** BSE Limited / BSE Information Products  
**Official documents:** [BSE corporate announcements page](https://www.bseindia.com/corporates/ann.html), [BSE Self Data Feed portal](https://marketdata.bseindia.com/), [BSE Information Products Domestic Tariff Sheet (February 2025 PDF)](https://www.bseindia.com/downloads1/Information_Products_Pricing_Sheet.pdf), [BSE Corporate Announcement Filing System circular](https://www.bseindia.com/markets/MarketInfo/DownloadAttach.aspx?attachedId=b31c397f-ad57-44d7-a9f4-1d52f0819e7e&id=20230630-12)

**Verified facts**

- BSE's Self Data Feed portal advertises a Corporate Data API including company financials, disclosures, corporate announcements, and actions. Its published onboarding flow is **register and complete KYC → select plans → agree pricing and agreements → pay and receive access**. It advertises a limited free trial for selected feeds and says feed details, formats, and manuals are available to help select a plan.
- BSE's February 2025 domestic tariff describes real-time/intraday corporate data and a historical corporate-data repository. It lists Corporate Announcements at **₹900,000/year for continuous** and **₹500,000/year for end-of-day**, before taxes, for the tariff's stated domestic datafeed customer scope. The pricing sheet is dated February 2025, so current pricing and contract scope must be reconfirmed.
- BSE's Corporate Announcement Filing System materials describe the **Listing Centre** as the issuer filing platform and say submitted announcements are disseminated directly to the BSE website. This documents issuer submission/dissemination flow, not a public consumer API.
- BSE official material directs listed companies to make announcement documents machine-readable/searchable. That helps extraction but does not guarantee uniform document quality or a structured API payload.

**Access method:** For a human, the official [announcements page](https://www.bseindia.com/corporates/ann.html) is the published browsing path. For programmatic use, BSE advertises a paid corporate-data API/feed through its Self Data Feed portal. The browser page is not a documented API contract; no endpoint or direct web request has been inferred here.  
**Authentication:** The paid feed requires registration/KYC and agreements; API credential mechanics are not publicly detailed on the portal. For the public web announcement page, this research did not verify a supported programmatic authentication method.  
**Available data:** BSE advertises announcements, financial results, shareholding patterns, corporate actions and other corporate data. The public tariff labels announcement feed as continuous or EOD. Fields, attachment-link format, company identifiers, correction/revision behavior, and whether full text is included in the API are **needs confirmation** from BSE's manual/trial.  
**Timestamps/history:** The tariff advertises real-time/intraday and historical corporate data. The public materials reviewed do not specify announcement timestamp fields, historical lookback depth, or update latency. Confirm those points and whether historical announcements/attachments are separately priced.  
**Rate limits/polling:** No public request-per-minute quota, delivery frequency, or polling guidance was found. Ask BSE whether its API is pull, push, or file-based, and whether its terms permit scheduled polling.  
**Licensing/pricing:** A plan and agreement are required for the advertised data feed. The February 2025 domestic tariff lists the fees above (excluding taxes); redistribution rights and use for NLP/training are not established by the product summary. Obtain the applicable current tariff and written agreement for internal use, derived outputs, customer display, retention, and redistribution.  
**Integration complexity:** Unknown until BSE supplies the technical manual. Likely medium-to-high for operational delivery because KYC, procurement, access credentials, historical coverage, schemas, and attachments need validation before a connector can be scoped.

**Suitability for SentimentIQ:** Important coverage source, especially for BSE-specific filings and cross-exchange completeness. Suitable after a trial confirms fields and the contract allows the intended analytics. Not the first low-friction source while public API schema and access mechanics remain unavailable.

## 3. Financial news providers

### 3.1 Upstox News API

**Provider:** Upstox  
**Official docs:** [Get News](https://upstox.com/developer/api-documentation/get-news/), [Authentication](https://upstox.com/developer/api-documentation/authentication/), [Rate limits](https://upstox.com/developer/api-documentation/rate-limiting/), [API error codes](https://upstox.com/developer/api-documentation/error-codes/)

**Verified facts:** The API is a REST `GET /v2/news` endpoint. It supports news by selected instrument keys, current positions, or holdings; requests can include up to 30 instrument keys. It returns articles from the previous seven days and supports pagination (page number 1–100; page size 1–100, default 100). Fields include headline, summary, thumbnail URL, article link, and published timestamp in Unix milliseconds.  
**Authentication:** Bearer access token. Upstox documents OAuth 2.0 authorization-code flow; app credentials and user login/approval are involved. Tokens are user-authorized, so this is not an anonymous server-to-server news key.  
**Rate limits:** Upstox publishes general “Other Standard APIs” limits of 50 requests/second, 500/minute, and 2,000 per 30 minutes per API/per user. The public limits page does not explicitly classify the newer News API endpoint in that category; the endpoint-specific quota should be confirmed with Upstox before setting a poller. HTTP 429 is documented for excessive requests.  
**Licensing:** The API docs establish technical access, not a clear right to store, train on, or redistribute article content or derived results. Confirm the news-content license and whether a user-authorized broker API may power an independent multi-user product.  
**Historical data:** The documented endpoint returns only a rolling seven-day window; deeper archive access is not stated.  
**Integration complexity:** Low-to-medium technically (REST + OAuth + instrument mapping), but medium/high operationally if tokens require user interaction/refresh and coverage is tied to individual user instruments.  
**Suitability:** A useful supplementary source for selected NSE-listed companies in a user-authorized context. Not a broad exchange-wide news feed; no public content-redistribution permission or long history was verified.

### 3.2 NewsAPI.org

**Provider:** NewsAPI.org  
**Official docs:** [Documentation](https://newsapi.org/docs), [Endpoints](https://newsapi.org/docs/endpoints), [Authentication](https://newsapi.org/docs/authentication), [Pricing](https://newsapi.org/pricing), [Terms](https://newsapi.org/terms)

**Verified facts:** REST endpoints include `/v2/everything` (search) and `/v2/top-headlines`; filters include keyword, publication date, source domain, language, and sort options. API responses expose article metadata and source URL; full article text is not supplied. Authentication is an API key, preferably in `X-Api-Key` or `Authorization` header rather than the URL.  
**Limits/freshness/history:** Developer plan: 100 requests/day, articles delayed by 24 hours, and search up to one month old; it has no uptime SLA. Business pricing displayed at research time: US$449/month with 250,000 requests/month and real-time articles, up to five years of search history; Advanced: US$1,749/month, 2,000,000 requests/month and 99.95% SLA. Confirm current quotations before purchase.  
**Licensing:** The free Developer plan is development/testing only and cannot be used in staging or production, including internal production. The terms prohibit reproducing/republishing copyrighted material and building a competing news database; underlying third-party content remains subject to the publisher's rights. The API does not include full article text. A paid plan does not by itself resolve each publisher's content rights—confirm retention, model training, and derived-output/display terms.  
**Rate limits:** Daily quota is published by plan; no separate per-second limit is established in the reviewed pricing/docs. Avoid treating plan quota as a permitted polling cadence.  
**Integration complexity:** Low (simple REST/key auth); medium operationally due quotas, delayed free data, source variance, and publisher-rights limitations.  
**Suitability:** Useful for development of search/query workflow only. Free plan is delayed and non-production. Commercially priced tiers may be considered later, but India business-source coverage, full text, and rights for model/derived data need validation.

### 3.3 TheNewsAPI.com

**Provider:** TheNewsAPI.com  
**Official docs:** [API documentation](https://www.thenewsapi.com/documentation), [Pricing](https://www.thenewsapi.com/pricing), [Terms of Service](https://www.thenewsapi.com/tos)

**Verified facts:** Documented REST endpoints include headlines, all-news search, similar stories, single article by UUID, and source lookup. Responses can include UUID, title, description, keywords, a short snippet (documented as first 60 characters of the article body), URL, image URL, language, publication datetime, source domain, categories, locale, and similarity metadata. Dates are UTC. Auth uses an API token in the query string.  
**Limits/freshness/history:** The pricing page advertises Free at 100 requests/day and 3 articles/request; Basic 2,500/day and 25 articles/request; Standard 10,000/day and 50 articles/request; Pro 25,000/day and 100 articles/request. It advertises real-time and historical data on each plan, but the public pricing page does not specify the historical lookback depth. The documentation reports HTTP 429 on too many requests in a rolling 60-second period and says the rate-limit headers expose the plan limit/remaining count; the actual per-minute number is not published in the reviewed docs.  
**Licensing:** The API documentation and pricing page alone do not establish commercial rights to store/reproduce publisher articles or train models on them. The site's Terms of Service include a limited personal/non-commercial site-content license and restrictions on commercial site use; their exact application to API data and paid subscriptions is not clear from the public documents reviewed. Obtain a written API/data license covering internal storage, model training, derived sentiment, and customer display before use.  
**Integration complexity:** Low-to-medium (REST, pagination and token; token in query string raises log-leak risk, so redact URLs). Medium source-quality work is needed to assess Indian finance coverage, language mix, duplicates, and snippets' utility.  
**Suitability:** Worth a small evaluation trial if Indian business/market sources are represented and a suitable written data license is offered. Not yet cleared for a commercial SentimentIQ pipeline.

## 4. Cross-provider operational and reliability considerations

These are implementation considerations, not provider guarantees:

1. **Source-of-record and attribution:** Preserve the publisher/exchange name, original item URL, identifiers, publication time, collection time, and all provider attribution. Exchange disclosures are valuable primary evidence; third-party news is secondary and can be corrected or removed.
2. **Timestamp semantics:** Store raw timestamp and timezone/precision as delivered. NSE's documented CA timestamp is minute precision; Upstox uses Unix milliseconds; TheNewsAPI documents UTC ISO dates. Do not compare “published,” “received,” and “disseminated” timestamps as if they meant the same event.
3. **Idempotence and corrections:** Use source IDs/URLs and payload hashes where permitted. Expect revisions, duplicate publications across NSE/BSE, multiple attachments, corrections, and identical articles syndicated across publishers. Confirm whether a provider emits update/delete notices.
4. **Backfill before real-time:** Confirm archival window, attachment retention, late arrivals, and historical entitlement. A realtime feed without an agreed replay/recovery path can lose announcements during outages.
5. **Resilience:** For paid feeds, request SLA/maintenance windows, failover, sequence-gap recovery, replay behavior, support contacts, and delivery reports. For REST/news APIs, honor quota headers, back off on 429/5xx, cache stable results, and monitor freshness and item counts.
6. **Rights model:** Separate rights to retrieve metadata, download attachments/full text, retain raw text, train/fine-tune models, retain embeddings, display excerpts, show attribution, and distribute derived scores. “Publicly accessible” and “API available” do not automatically grant each right.
7. **Commercial product design:** Keep source evidence links and attribution in the product. Avoid displaying full source articles or redistributing exchange feeds until the respective contract expressly permits it.
8. **India coverage/language:** Ask each news vendor for a source list and sample coverage for Indian listed issuers, including English and Indian-language sources, entity-to-instrument mapping, source correction practices, and how syndicated copies are represented.

## 5. Open questions to resolve before writing connectors

### NSE RSS

- What are the current official announcement RSS URL(s), item fields, stable IDs, attachment links, and feed retention behavior?
- Is unattended server-side polling permitted? What refresh interval and user agent are expected?
- May SentimentIQ retain feed entries/attachments, analyze them with NLP, retain evidence excerpts, and display derived sentiment to users? What attribution and retention rules apply?

### NSE paid feed

- Confirm current prices, taxes, one-time connectivity costs, subscriber eligibility, onboarding timeline, and fees for both realtime and EOD scopes.
- Confirm archive/backfill duration, event replay after sequence gaps/outages, update/correction semantics, attachment retrieval limits, and exact EOD production time.
- Ensure the agreement expressly covers model analysis, raw-text retention, derived outputs, public display, and redistribution if needed.

### BSE

- Request the current corporate-announcement API/feed manual and trial, including API base/interface, auth, payload schema, identifiers, timestamps/time zones, pagination/stream mechanics, attachments, historical depth, rate limits, and correction/deletion behavior.
- Confirm latest tariff and license terms, including commercial/internal analytics, NLP/model training, derivative sentiment display, storage, end-user count, redistribution, and attribution.

### News providers

- Run a small, permitted source-coverage evaluation for Indian issuers before choosing a paid plan.
- Obtain the data/content license in writing for each vendor, particularly full-text retention and machine-learning use.
- Verify any per-minute throttles, SLA, regional source list, data residency/retention, and cancellation/export rules before relying on a provider in production.

## 6. Recommendation: first source for the MVP

**Start with the official NSE announcements RSS feed as a limited internal feasibility pilot, after NSE confirms the actual feed URL/schema, allowed automated refresh interval, and rights for storage and NLP analysis.** It is the lowest-friction primary-source option publicly advertised by an exchange, directly fits the company-announcement use case, and avoids building against undocumented browser endpoints. Treat the RSS as a discovery/notification stream: retain only what the confirmed terms allow and link to the official filing for evidence.

If NSE does not authorize the intended automated/model use, do not fall back to scraping the announcements page. The next route is to scope the licensed NSE EOD Corporate Announcement product (published at ₹500,000/year domestic, subject to reconfirmation), or obtain a BSE data-feed trial and compare its licensed fields and historical coverage. The official NSE EOD files are structurally documented and include announcement details, timestamp, and attachment filename, but are daily rather than intraday; NSE realtime is a separate, higher-cost leased-line feed. Third-party news can supplement disclosures after rights and India coverage are verified; it should not replace exchange filings as the source of record.

## Official source register

- NSE RSS: https://www.nseindia.com/static/rss-feed
- NSE announcement search page: https://www.nseindia.com/companies-listing/corporate-filings-announcements
- NSE paid corporate data: https://www.nseindia.com/static/market-data/corporate-data-subscription
- NSE usage policy: https://www.nseindia.com/static/market-data/nse-data-policy
- NSE Data corporate feed specification: https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Download_Technical_Specification_Corporate_Data.pdf
- NSE Data EOD specification: https://nsearchives.nseindia.com/web/sites/default/files/inline-files/EOD_DATA-Corporate_EODv1.2.pdf
- BSE announcements page: https://www.bseindia.com/corporates/ann.html
- BSE data-feed portal: https://marketdata.bseindia.com/
- BSE tariff PDF: https://www.bseindia.com/downloads1/Information_Products_Pricing_Sheet.pdf
- Upstox news docs: https://upstox.com/developer/api-documentation/get-news/
- NewsAPI.org docs/pricing/terms: https://newsapi.org/docs | https://newsapi.org/pricing | https://newsapi.org/terms
- TheNewsAPI docs/pricing/terms: https://www.thenewsapi.com/documentation | https://www.thenewsapi.com/pricing | https://www.thenewsapi.com/tos
