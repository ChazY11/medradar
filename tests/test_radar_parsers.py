"""Adapter parsers: real source payload shapes, parsed offline.

The fixtures here are trimmed excerpts of payloads that the live probe actually received
(PubMed XML, a Crossref work object, the Philips news index, the Dräger newsroom sitemap).
Tests are offline so a schema change in a source is caught by the parser's own assertions
rather than by a nightly job.
"""

from __future__ import annotations

from pathlib import Path

from medradar.radar.adapters.crossref import _record_from_item
from medradar.radar.adapters.draeger import _sitemap_entries
from medradar.radar.adapters.philips import _press_links
from medradar.radar.adapters.pubmed import _articles, _record_from_article, primary_vendor_affiliation
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"

PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">39123456</PMID>
      <Article>
        <Journal>
          <JournalIssue>
            <PubDate><Year>2026</Year><Month>Mar</Month></PubDate>
          </JournalIssue>
          <Title>Critical Care Medicine</Title>
        </Journal>
        <ArticleTitle>Alarm fatigue and <i>signal quality</i> in intensive care monitoring.</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Alarm fatigue is a persistent problem.</AbstractText>
          <AbstractText Label="RESULTS">A modular patient monitor reduced false alarms.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Doe</LastName>
            <ForeName>Jane</ForeName>
            <AffiliationInfo><Affiliation>Philips Research, Eindhoven, NL</Affiliation></AffiliationInfo>
          </Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>Monitoring, Physiologic</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1097/CCM.0000000000005001</ArticleId>
        <ArticleId IdType="pubmed">39123456</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>39123457</PMID>
      <Article>
        <Journal>
          <JournalIssue><PubDate><MedlineDate>2026 Spring</MedlineDate></PubDate></JournalIssue>
          <Title>Some Journal</Title>
        </Journal>
        <ArticleTitle>SpO2 thresholds in the ICU</ArticleTitle>
        <ArticleDate><Year>2026</Year><Month>04</Month><Day>09</Day></ArticleDate>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""

CROSSREF_ITEM = {
    "DOI": "10.1097/CCM.0000000000005001",
    "title": ["Alarm fatigue and signal quality in intensive care monitoring."],
    "container-title": ["Critical Care Medicine"],
    "abstract": "<jats:p>A modular patient monitor reduced false alarms.</jats:p>",
    "author": [
        {"given": "Jane", "family": "Doe",
         "affiliation": [{"name": "Philips Research, Eindhoven, NL"}]},
    ],
    "published-online": {"date-parts": [[2026, 4, 9]]},
    "created": {"date-time": "2026-04-10T02:00:00Z"},
    "publisher": "Ovid Technologies (Wolters Kluwer Health)",
    "type": "journal-article",
    "subject": ["Critical Care and Intensive Care Medicine"],
}

PHILIPS_INDEX = """
<div class="grid">
  <a href="https://www.philips.com/a-w/about/news/archive/standard/news/press/2026/philips-launches-hypervue-integrated-system.html">One</a>
  <a href="https://www.philips.com/a-w/about/news/archive/standard/news/press/2026/philips-launches-hypervue-integrated-system.html">Duplicated</a>
  <a href="https://www.philips.com/a-w/about/news/archive/standard/news/press/2026/philips-launches-uniguide-3d.html">Two</a>
  <a href="https://www.philips.com/content/corporate/en_AA/feed.rss.xml">Disallowed path, must be ignored</a>
</div>
"""

DRAEGER_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.draeger.com/en_uk/Newsroom/About-Draeger/silent-intensive-care-unit</loc>
    <lastmod>2026-06-02T09:36:46+00:00</lastmod>
  </url>
  <url>
    <loc>https://www.draeger.com/en_uk/Newsroom/About-Draeger/clean-energy</loc>
    <lastmod>2025-08-12T07:18:03+00:00</lastmod>
  </url>
</urlset>
"""


def test_pubmed_xml_yields_title_abstract_authors_and_a_real_doi():
    articles = _articles(PUBMED_XML)
    assert len(articles) == 2
    record = _record_from_article(articles[0])
    assert record.source_record_id == "pmid:39123456"
    assert record.official_identifier == "PMID:39123456"
    assert "Alarm fatigue" in record.title
    assert "<i>" not in record.title, "markup must be stripped from the title"
    assert record.payload["doi"] == "10.1097/CCM.0000000000005001"
    assert record.payload["journal"] == "Critical Care Medicine"
    assert record.payload["authors"] == ["Jane Doe"]
    assert record.payload["affiliations"] == ["Philips Research, Eindhoven, NL"]
    # Month-name pub date with no day: a year precision, never an invented day.
    assert record.published_at == "2026-03"


def test_pubmed_prefers_articledate_over_pubdate():
    record = _record_from_article(_articles(PUBMED_XML)[1])
    assert record.published_at == "2026-04-09"
    assert record.published_at_precision == "date"


def test_pubmed_affiliation_hint_only_names_a_monitored_vendor():
    affiliations = ["Philips Research, Eindhoven", "Some University"]
    assert primary_vendor_affiliation(affiliations) == "Philips Research, Eindhoven"
    assert primary_vendor_affiliation(["Some University"]) is None


def test_crossref_item_maps_doi_title_and_strips_jats_markup():
    record = _record_from_item(CROSSREF_ITEM)
    assert record is not None
    assert record.official_identifier == "DOI:10.1097/ccm.0000000000005001"
    assert record.url == "https://doi.org/10.1097/CCM.0000000000005001"
    assert record.published_at == "2026-04-09"
    assert "<jats:p>" not in record.payload["abstract"]
    assert record.payload["created_at"].startswith("2026-04-10")


def test_crossref_item_without_a_doi_is_rejected_rather_than_guessed():
    assert _record_from_item({"title": ["No DOI here"]}) is None


def test_philips_index_links_deduplicate_and_never_include_a_disallowed_path():
    links = _press_links(PHILIPS_INDEX)
    ids = [link["record_id"] for link in links]
    assert len(ids) == 2, "the duplicate link must collapse to one record"
    assert all("/content/" not in link["url"] for link in links), (
        "robots.txt disallows /content/ and this adapter must never request it"
    )


def test_draeger_sitemap_parses_loc_and_lastmod():
    entries = _sitemap_entries(DRAEGER_SITEMAP)
    assert len(entries) == 2
    assert entries[0]["record_id"].startswith("draeger:en_uk/newsroom/")
    assert entries[0]["lastmod"].startswith("2026-06-02")


def test_every_adapter_targets_a_declared_source_id():
    from medradar.radar.adapters import FACTORIES

    taxonomy = load_taxonomy(str(CONFIG_DIR))
    declared = {source["id"] for source in taxonomy.sources()}
    assert set(FACTORIES) == declared, (
        "every adapter must have a config entry and every config entry an adapter"
    )
