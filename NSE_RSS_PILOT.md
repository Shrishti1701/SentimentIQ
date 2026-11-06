# NSE RSS Feasibility Pilot

**Checked:** 4 November 2026  
**Scope:** Read-only retrieval and parsing of the official NSE corporate-announcements RSS feed. No connector integration, persistence, model use, or redistribution was performed.

## Result

The RSS route is technically feasible for a limited pilot. The standalone script received an HTTP 200 response from NSE's archive host, parsed the XML with `feedparser`, and retrieved **546 records** in the response. The first 20 were printed; the script did not write records to disk or send them elsewhere.

## Official source and URL

- NSE's [official RSS documentation](https://www.nseindia.com/static/rss-feed) lists **Corporate Information → Announcements** and instructs users to subscribe by selecting the corresponding RSS icon. It describes RSS as a headline/summary feed and says users receive the latest posted information, while warning that feed-reader/service-provider delays can occur.
- URL used for this read-only test: [`https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml`](https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml). This is served from NSE's `nsearchives.nseindia.com` host. The URL is consistent with the official Announcements feed and returned an XML response during the run. The official RSS directory itself does not print the endpoint as ordinary text, so verify the icon's current target again if NSE changes its directory implementation.
- The official [corporate filings page](https://www.nseindia.com/companies-listing/corporate-filings-announcements) is the companion browser view for NSE announcements.

## HTTP and parser results

| Check | Observed result |
|---|---|
| HTTP status | `200 OK` |
| Content-Type | `application/xml` |
| Feed title | `NSE News - Latest Announcements` |
| Records parsed | **546** |
| Parse warning | None reported (`feedparser` did not mark the response malformed) |
| Displayed | First 20 records, with title, link, publication date, and summary/description |
| Persistence | None; response was held in memory for display only |

The first record at test time was “Balmer Lawrie & Company Limited,” published as `04-Nov-2026 11:59:36`; it linked to an NSE-hosted filing document. This is an observed sample, not a guarantee about feed ordering or future output.

### Fields exposed by this response

`feedparser` reported these entry fields: `title`, `link`, `published`, `published_parsed`, `summary`, `summary_detail`, `title_detail`, and `links`.

- `title`: company name in the observed records.
- `link`: direct filing/attachment URL, commonly PDF; some records may link to XML or other file types.
- `published`: display string such as `04-Nov-2026 11:59:36`.
- `published_parsed`: parsed date tuple.
- `summary`: announcement description text; observed summaries often include the filing description and a `SUBJECT:` label.
- `description`: no separate `description` key was present in this response; the script falls back to `summary` for display.

The feed entry does not expose a distinct company symbol, source-received timestamp, dissemination timestamp, or stable item ID in the fields observed. The public NSE announcement webpage may show additional columns, but they should not be assumed to exist in RSS. The publication date string has no explicit timezone marker in the observed entry; confirm its timezone/semantics with NSE before converting or comparing it.

## Errors and access notes

The first run from the restricted shell could not open an outbound socket (`WinError 10013`). That was a local execution-environment network restriction; it did not return an NSE HTTP response. The same script was then run through the approved network-enabled path and successfully received the `200 OK` response above. No NSE authentication wall, 401, 403, CAPTCHA, or feed error was observed, and no access-control bypass was attempted.

The script handles request timeouts and network exceptions, HTTP errors (including an explicit 401/403 stop), empty responses, malformed XML, and feeds with zero parsed entries. It prints at most 20 records to keep console output bounded while reporting the full parsed count.

## Polling limitations

NSE's RSS documentation describes the feed as a real-time listing of the latest posted items, but explicitly notes that third-party feed readers/services can introduce delays. It does **not** publish a numeric rate limit, an automated-client polling interval, a freshness SLA, or a retention/backfill guarantee. No official polling interval was verified in this pilot. Do not convert the observed 546 entries or current access result into an approved polling policy; ask NSE for permitted automated refresh frequency and recovery expectations before continuous polling.

## Licensing and usage questions still open

The RSS page documents subscription and headline/summary delivery, but the sources reviewed do not explicitly grant SentimentIQ rights to:

- retain the RSS summaries or filing metadata in a database;
- download or retain linked announcement documents;
- analyze content with NLP or use it for model training/evaluation;
- display excerpts, attribution, or derived sentiment to third parties;
- redistribute feed items or keep them after correction/removal.

The prior [data-source research](DATA_SOURCE_RESEARCH.md) records these as outstanding. Obtain written clarification from NSE covering automated collection, polling, retention, NLP/model use, derived outputs, attribution, and customer display before production use.

## Recommendation

Proceed with a **limited, manual/local feasibility pilot**: the URL is reachable through the approved network path, the feed parses cleanly, and its title/link/date/summary fields are useful for discovery. Do **not** proceed to a production connector yet. Production approval depends on NSE confirming automated polling limits, timestamp semantics, stable feed behavior/backfill, and the licensing scope for storage and NLP-derived insights. If those permissions are not granted, do not scrape the announcement website as a substitute.

## Re-run

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m ingestion.nse_rss_test
```

The script is standalone and does not persist or redistribute feed content. Its source is [ingestion/nse_rss_test.py](ingestion/nse_rss_test.py).
