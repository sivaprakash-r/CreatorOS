"""Browser tests (Playwright). Ordered: seed → brief → detail → publish → feedback → learn."""

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.ui


def select_by_text(page: Page, selector: str, text: str) -> None:
    value = page.locator(f"{selector} option", has_text=text).first.get_attribute("value")
    page.locator(selector).select_option(value)


def test_dashboard_loads_and_seeds_demo(page: Page, server_url):
    page.goto(server_url + "/#/dashboard")
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
    expect(page.locator("#foot")).to_contain_text("Mesh API")
    seed = page.locator("#seed")
    if seed.count():
        seed.click()
        expect(seed).to_be_hidden(timeout=30000)
    page.goto(server_url + "/#/brands")
    expect(page.get_by_test_id("brand-list")).to_contain_text("Techsivam Labs")
    expect(page.get_by_test_id("brand-list")).to_contain_text("Sunny Side Bakes")


def test_create_brand_via_form(page: Page, server_url):
    page.goto(server_url + "/#/brands")
    page.locator("#add").click()
    page.get_by_test_id("brand-name").fill("UI Test Brand")
    page.get_by_test_id("brand-desc").fill("created from the browser test")
    page.get_by_test_id("brand-sample-0").fill("Most teams get testing wrong. Here is what works for us in practice.")
    page.get_by_test_id("brand-sample-1").fill("We measured it for 30 days and wrote the decision down. Which do you do?")
    page.get_by_test_id("brand-save").click()
    expect(page.get_by_test_id("brand-list")).to_contain_text("UI Test Brand", timeout=30000)
    expect(page.get_by_test_id("brand-list")).to_contain_text("2 samples")


def test_brief_to_detail_with_editor_diff_and_trail(page: Page, server_url):
    page.goto(server_url + "/#/new")
    select_by_text(page, "[data-testid=brief-brand]", "Techsivam")
    page.get_by_test_id("brief-text").fill("a LinkedIn post about AI safety for engineering leaders")
    page.get_by_test_id("brief-submit").click()
    page.wait_for_url(re.compile(r"#/content/\w+"), timeout=15000)
    expect(page.get_by_test_id("detail-brief")).to_contain_text("AI safety")
    # pipeline runs in the background; the page polls until ready
    expect(page.locator(".pill.ready")).to_be_visible(timeout=60000)
    expect(page.get_by_test_id("final-text")).not_to_contain_text("(not ready)")
    expect(page.get_by_test_id("diff")).to_be_visible()  # the editor loop changed the text
    expect(page.get_by_test_id("diff").locator("ins").first).to_be_visible()
    timeline = page.get_by_test_id("timeline")
    for agent in ("strategist", "writer", "editor", "visual", "evaluator"):
        expect(timeline.locator(f".agent.{agent}").first).to_be_visible()
    expect(timeline).to_contain_text("Required edits")
    expect(page.get_by_test_id("quality-after")).not_to_have_text("—")
    expect(page.get_by_test_id("image")).to_be_visible()


def test_publish_and_record_performance(page: Page, server_url):
    page.goto(server_url + "/#/content")
    page.locator("tr.link").first.click()
    page.wait_for_url(re.compile(r"#/content/\w+"))
    expect(page.locator(".pill.ready")).to_be_visible(timeout=60000)
    page.get_by_test_id("btn-publish").click()
    expect(page.locator(".pill.published")).to_be_visible(timeout=15000)
    page.get_by_test_id("btn-feedback").click()
    page.get_by_test_id("pf-impressions").fill("4000")
    page.get_by_test_id("pf-likes").fill("220")
    page.get_by_test_id("pf-comments").fill("31")
    page.get_by_test_id("btn-feedback-ok").click()
    expect(page.locator("#toast")).to_contain_text("Performance recorded")
    expect(page.locator("table").last).to_contain_text("user")


def test_schedule_flow(page: Page, server_url):
    page.goto(server_url + "/#/new")
    select_by_text(page, "[data-testid=brief-brand]", "Techsivam")
    page.get_by_test_id("brief-text").fill("why observability beats cleverness")
    page.get_by_test_id("brief-submit").click()
    page.wait_for_url(re.compile(r"#/content/\w+"), timeout=15000)
    expect(page.locator(".pill.ready")).to_be_visible(timeout=60000)
    page.locator("#btn-schedule").click()
    page.locator("#sched-at").fill("2020-01-01T09:00")  # in the past → scheduler publishes it on its next poll
    page.get_by_test_id("btn-schedule-ok").click()
    expect(page.locator(".pill.scheduled, .pill.published").first).to_be_visible(timeout=10000)
    page.wait_for_timeout(4000)  # SCHEDULER_POLL_SECONDS=2 in the test server
    page.reload()
    expect(page.locator(".pill.published")).to_be_visible(timeout=15000)


def test_learning_cycle_page(page: Page, server_url):
    page.goto(server_url + "/#/learnings")
    expect(page.get_by_role("heading", name="Learnings")).to_be_visible()
    select_by_text(page, "#bsel", "Techsivam")
    page.wait_for_url(re.compile(r"#/learnings/\w+"))
    page.locator("#plat").select_option("linkedin")
    page.get_by_test_id("btn-learn").click()
    expect(page.locator("#toast")).to_contain_text("Learned from", timeout=30000)
    expect(page.locator("h2", has_text="Active rules")).to_contain_text(re.compile(r"Active rules \([1-9]"))
    expect(page.locator(".bar")).to_have_count(2, timeout=5000)


def test_decision_trail_page_filters(page: Page, server_url):
    page.goto(server_url + "/#/decisions")
    expect(page.get_by_test_id("timeline")).to_be_visible()
    page.locator("#agent").select_option("editor")
    expect(page.locator("#tl .agent").first).to_have_text("editor")
    assert page.locator("#tl .agent.strategist").count() == 0


def test_pipeline_strip_agent_log_and_example_brief(page: Page, server_url):
    page.goto(server_url + "/#/new")
    select_by_text(page, "[data-testid=brief-brand]", "Sunny Side")
    page.locator("#use-example").click()
    expect(page.get_by_test_id("brief-text")).to_have_value(re.compile("café-style coffee"))
    expect(page.get_by_test_id("plat-instagram")).to_be_checked()
    expect(page.get_by_test_id("plat-linkedin")).not_to_be_checked()
    page.get_by_test_id("brief-submit").click()
    page.wait_for_url(re.compile(r"#/content/\w+"), timeout=15000)
    expect(page.locator(".pill.ready")).to_be_visible(timeout=60000)
    strip = page.get_by_test_id("pipeline")
    for stage in ("strategist", "writer", "editor", "visual", "scoring"):
        expect(strip.locator(f"[data-stage={stage}]")).to_have_class(re.compile("done"))
    expect(strip).to_contain_text("round")
    expect(page.get_by_test_id("agent-log")).to_contain_text("Mesh API")
    expect(page.get_by_test_id("llm-totals")).to_contain_text("LLM calls")
    page.locator("#btn-schedule").click()
    expect(page.get_by_test_id("slot-reason")).to_contain_text("Why:")


def test_platform_preview_and_replay(page: Page, server_url):
    # the instagram piece from the previous test → carousel preview
    page.goto(server_url + "/#/content")
    page.locator("tr.link", has_text="Instagram").first.click()
    page.wait_for_url(re.compile(r"#/content/\w+"))
    expect(page.locator(".pill.ready")).to_be_visible(timeout=60000)
    page.get_by_test_id("pv-preview").click()
    car = page.get_by_test_id("preview-instagram")
    expect(car).to_be_visible()
    expect(car.locator(".slide.on")).to_have_count(1)
    car.locator("[data-car='1']").click()
    expect(car.locator(".slide.on .n")).to_have_text(re.compile(r"^2/"))
    page.get_by_test_id("pv-raw").click()
    expect(page.get_by_test_id("final-text")).to_be_visible()
    page.get_by_test_id("pv-preview").click()
    # replay: step through decisions one at a time
    page.get_by_test_id("rp-next").click()
    expect(page.get_by_test_id("stage-panel")).to_contain_text("strategist")
    expect(page.get_by_test_id("pipeline").locator("[data-stage=strategist]")).to_have_class(re.compile("active"))
    page.get_by_test_id("rp-next").click()
    page.get_by_test_id("rp-next").click()
    expect(page.get_by_test_id("stage-panel")).to_contain_text("Required edits")
    expect(page.get_by_test_id("replay")).to_contain_text("step 3/")
    page.get_by_test_id("rp-play").click()
    expect(page.get_by_test_id("replay")).to_contain_text("full run", timeout=30000)
    # linkedin piece → see more fold
    page.goto(server_url + "/#/content")
    page.locator("tr.link", has_text="LinkedIn").first.click()
    page.wait_for_url(re.compile(r"#/content/\w+"))
    expect(page.get_by_test_id("preview-linkedin")).to_be_visible(timeout=60000)
    if page.locator("[data-more]").count():
        page.locator("[data-more]").click()
        expect(page.locator(".pv-full")).to_be_visible()
