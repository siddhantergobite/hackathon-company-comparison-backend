"""Seed MongoDB with realistic (but FICTIONAL) test events.

    python -m backend.events.scripts.seed_events            # insert / refresh
    python -m backend.events.scripts.seed_events --reset    # delete previous seed events first

Events are fictional: organizers are made up and links use the reserved example.com
domain, so nothing here pretends to be a real event. Dates are relative to today so the
data set is always "upcoming". Seed events go through the same pipeline as real sources.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.events.database import ensure_indexes, get_db  # noqa: E402
from backend.events.services import event_service as svc  # noqa: E402
from backend.events.processors.pipeline import ingest_event  # noqa: E402

SOURCE = "Seed Data"

CITIES = {
    "San Francisco": ("California", "USA", 37.7749, -122.4194, "America/Los_Angeles"),
    "New York": ("New York", "USA", 40.7128, -74.0060, "America/New_York"),
    "Austin": ("Texas", "USA", 30.2672, -97.7431, "America/Chicago"),
    "Boston": ("Massachusetts", "USA", 42.3601, -71.0589, "America/New_York"),
    "Chicago": ("Illinois", "USA", 41.8781, -87.6298, "America/Chicago"),
    "London": ("England", "UK", 51.5074, -0.1278, "Europe/London"),
    "Berlin": ("Berlin", "Germany", 52.5200, 13.4050, "Europe/Berlin"),
    "Paris": ("Île-de-France", "France", 48.8566, 2.3522, "Europe/Paris"),
    "Amsterdam": ("North Holland", "Netherlands", 52.3676, 4.9041, "Europe/Amsterdam"),
    "Lisbon": ("Lisbon", "Portugal", 38.7223, -9.1393, "Europe/Lisbon"),
    "Bengaluru": ("Karnataka", "India", 12.9716, 77.5946, "Asia/Kolkata"),
    "Mumbai": ("Maharashtra", "India", 19.0760, 72.8777, "Asia/Kolkata"),
    "Singapore": (None, "Singapore", 1.3521, 103.8198, "Asia/Singapore"),
    "Tokyo": ("Tokyo", "Japan", 35.6762, 139.6503, "Asia/Tokyo"),
    "Dubai": ("Dubai", "UAE", 25.2048, 55.2708, "Asia/Dubai"),
    "Sydney": ("New South Wales", "Australia", -33.8688, 151.2093, "Australia/Sydney"),
    "Toronto": ("Ontario", "Canada", 43.6532, -79.3832, "America/Toronto"),
    "São Paulo": ("São Paulo", "Brazil", -23.5505, -46.6333, "America/Sao_Paulo"),
    "Lagos": ("Lagos", "Nigeria", 6.5244, 3.3792, "Africa/Lagos"),
    "Nairobi": ("Nairobi", "Kenya", -1.2921, 36.8219, "Africa/Nairobi"),
}


def _description(title: str, topics: list[str], audience: list[str], summary: str) -> str:
    agenda = "\n".join(f"- {t}: talks, live demos and a Q&A with practitioners" for t in topics[:4])
    return (
        f"{summary} {title} brings together {', '.join(a.lower() for a in audience[:3])} for focused sessions, "
        "hands-on workshops and time to meet peers working on the same problems.\n\n"
        f"What to expect:\n{agenda}\n\n"
        "Sessions are curated by a program committee and recorded for registered attendees. "
        "This is a fictional event created for testing the Global Event Aggregator."
    )


def _event(n, title, etype, offset, days, city, venue, address, cats, topics, aud, org, summary, *,
           price=None, currency="USD", fmt="offline", start="09:00", end="17:30", status=None,
           image=True, org_desc=True, coords=True, long_desc=True):
    state, country, lat, lon, tz = CITIES[city] if city else (None, None, None, None, "UTC")
    start_day = date.today() + timedelta(days=offset)
    slug = title.lower().replace("&", "and").replace(" ", "-").replace(",", "")
    online = fmt == "online"
    raw = {
        "title": title,
        "event_type": etype,
        "summary": summary,
        "description": _description(title, topics, aud, summary) if long_desc else None,
        "start_date": start_day.isoformat(),
        "end_date": (start_day + timedelta(days=days - 1)).isoformat(),
        "start_time": start,
        "end_time": end,
        "timezone": tz if not online else "UTC",
        "location": (
            {"venue": None, "address": None, "city": None, "state": None, "country": None}
            if online else
            {"venue": venue, "address": address, "city": city, "state": state, "country": country,
             "latitude": lat if coords else None, "longitude": lon if coords else None}
        ),
        "format": fmt,
        "categories": cats,
        "topics": topics,
        "audience": aud,
        "organizer": {
            "name": org,
            "description": f"{org} runs professional events and communities. (Fictional organizer for test data.)" if org_desc else None,
            "website": f"https://example.com/{org.lower().replace(' ', '-')}",
            "social_links": {"linkedin": f"https://www.linkedin.com/company/{org.lower().replace(' ', '-')}", "x": f"https://x.com/{org.lower().replace(' ', '')}"} if org_desc else {},
        },
        "registration": {
            "url": f"https://example.com/events/{slug}/register",
            "price": price,
            "currency": currency if price else None,
            "ticket_type": "free" if not price else "paid",
            "ticket_info": "Early-bird pricing available until 30 days before the event." if price else "Free to attend; registration required.",
        },
        "image_url": f"https://picsum.photos/seed/{slug}/1200/630" if image else None,
        "event_url": f"https://example.com/events/{slug}",
        "source": {"name": SOURCE, "url": "https://example.com/seed", "source_event_id": f"seed-{n:03d}"},
    }
    if status:
        raw["status"] = status
    return raw, f"evt_{n:03d}"


def seed_events() -> list[tuple[dict, str]]:
    E = _event
    return [
        E(1, "AI & ML Summit 2026", "summit", 21, 3, "San Francisco", "Moscone Center", "747 Howard Street",
          ["Artificial Intelligence", "Machine Learning", "Technology"], ["Generative AI", "LLM", "AI Agents", "Computer Vision"],
          ["Founders", "CTOs", "Developers", "Researchers"], "Northwind Events",
          "A global summit on the latest developments in artificial intelligence and machine learning.", price=599),
        E(2, "FinTech Forward Conference", "conference", 34, 2, "London", "ExCeL London", "Royal Victoria Dock",
          ["FinTech", "Finance", "Blockchain"], ["Open Banking", "Payments", "Digital Assets", "RegTech"],
          ["Executives", "Investors", "Product Managers"], "Meridian Conferences",
          "Two days on the future of payments, open banking and regulation.", price=449, currency="GBP"),
        E(3, "Bengaluru Startup Founders Meetup", "meetup", 6, 1, "Bengaluru", "The Hive Coworking", "12 Indiranagar Main Road",
          ["Startups", "Entrepreneurship"], ["Fundraising", "Hiring", "Go-to-market"], ["Founders", "Entrepreneurs"],
          "Silk Route Ventures", "A relaxed monthly meetup for early-stage founders to swap notes.", start="18:30", end="21:00"),
        E(4, "Cloud Security Seminar", "industry_seminar", 12, 1, "New York", "Javits Center", "429 11th Ave",
          ["Cybersecurity", "Cloud"], ["Zero Trust", "Cloud Posture", "Incident Response"], ["CTOs", "Engineers"],
          "Bluefield Security Group", "An industry seminar on securing multi-cloud environments.", price=199),
        E(5, "Global HealthTech Expo", "expo", 48, 3, "Dubai", "Dubai World Trade Centre", "Sheikh Zayed Road",
          ["HealthTech", "Healthcare"], ["Telehealth", "Medical Devices", "Digital Health Records"],
          ["Business Leaders", "Investors", "Researchers"], "Harbor Expo Group",
          "An expo showcasing digital health products from over 200 exhibitors.", price=120, currency="AED"),
        E(6, "SaaS Growth Workshop", "workshop", 9, 1, "Austin", "Capital Factory", "701 Brazos St",
          ["SaaS", "Sales", "Marketing"], ["Pricing", "Onboarding", "Churn", "PLG"], ["Founders", "Marketers", "Sales Professionals"],
          "Growthlab Collective", "A hands-on workshop on pricing and retention for SaaS teams.", price=249),
        E(7, "Berlin Product Management Days", "conference", 63, 2, "Berlin", "Station Berlin", "Luckenwalder Str. 4-6",
          ["Product Management", "Software"], ["Roadmaps", "Discovery", "Experimentation"], ["Product Managers", "Designers"],
          "Spree Product Community", "Practical talks for product managers building B2B software.", price=350, currency="EUR"),
        E(8, "Data Science Online Bootcamp", "training", 14, 5, None, None, None,
          ["Data Science", "Machine Learning", "Education"], ["Python", "Feature Engineering", "MLOps"], ["Data Scientists", "Students"],
          "Insight Academy", "A five-day live online bootcamp covering the modern data science stack.", price=299, fmt="online", start="16:00", end="19:00"),
        E(9, "Crypto & Blockchain Builders Hackathon", "hackathon", 27, 2, "Singapore", "Marina Bay Sands Expo", "10 Bayfront Ave",
          ["Blockchain", "Technology"], ["Smart Contracts", "Layer 2", "DeFi"], ["Developers", "Engineers"],
          "Lionfish Labs", "A 48-hour hackathon with mentors and prizes for the best on-chain apps.", start="10:00", end="10:00"),
        E(10, "E-commerce Leaders Summit", "summit", 41, 2, "Toronto", "Metro Toronto Convention Centre", "255 Front St W",
          ["E-commerce", "Retail", "Marketing"], ["Marketplaces", "Logistics", "Personalisation"], ["Business Leaders", "Marketers"],
          "Maple Commerce Network", "Strategy sessions for retail and e-commerce executives.", price=520, currency="CAD"),
        E(11, "Women in Tech Networking Evening", "business_networking", 5, 1, "Sydney", "Barangaroo House", "35 Barangaroo Ave",
          ["Technology", "Human Resources"], ["Mentoring", "Careers", "Leadership"], ["Engineers", "Executives"],
          "Harbourside Tech Network", "An evening of networking and mentoring for women in technology.", start="17:30", end="20:30"),
        E(12, "Logistics & Supply Chain Trade Show", "trade_show", 76, 3, "Chicago", "McCormick Place", "2301 S King Dr",
          ["Logistics", "Manufacturing"], ["Warehouse Automation", "Freight Tech", "Last Mile"], ["Business Leaders", "Engineers"],
          "Prairie Trade Events", "North America's showcase for supply chain technology.", price=75),
        E(13, "Demo Day: Spring Startup Cohort", "startup_event", 18, 1, "Lisbon", "LX Factory Hall", "R. Rodrigues de Faria 103",
          ["Startups", "Investment"], ["Pitching", "Seed Funding", "Portfolio Companies"], ["Investors", "Founders"],
          "Tagus Accelerator", "Twelve startups pitch to investors at the end of the accelerator program.", start="14:00", end="18:00"),
        E(14, "Cybersecurity Leadership Webinar", "webinar", 3, 1, None, None, None,
          ["Cybersecurity", "Business"], ["Board Reporting", "Risk", "Ransomware"], ["Executives", "CTOs"],
          "Bluefield Security Group", "A one-hour webinar on communicating cyber risk to the board.", fmt="online", start="15:00", end="16:00"),
        E(15, "Energy Transition Conference", "conference", 55, 3, "Amsterdam", "RAI Amsterdam", "Europaplein 24",
          ["Energy", "Technology"], ["Grid Storage", "Hydrogen", "Solar"], ["Business Leaders", "Researchers", "Investors"],
          "Delta Energy Forum", "Three days on grids, storage and the economics of decarbonisation.", price=690, currency="EUR"),
        E(16, "Tokyo Robotics & Automation Expo", "expo", 82, 3, "Tokyo", "Tokyo Big Sight", "3-11-1 Ariake",
          ["Manufacturing", "Technology"], ["Industrial Robots", "Vision Systems", "Edge AI"], ["Engineers", "Business Leaders"],
          "Sakura Expo Partners", "Robotics and factory automation exhibitors from across Asia.", price=30, currency="USD"),
        E(17, "Lagos Tech & Innovation Week", "conference", 96, 4, "Lagos", "Eko Convention Centre", "Plot 1415 Adetokunbo Ademola St",
          ["Technology", "Startups", "FinTech"], ["Mobile Money", "Startup Ecosystem", "Talent"], ["Founders", "Developers", "Investors"],
          "Atlantic Innovation Hub", "A week of talks and side events celebrating African technology.", price=80),
        E(18, "Real Estate Investment Networking Breakfast", "business_networking", 8, 1, "Boston", "The Langham", "250 Franklin St",
          ["Real Estate", "Investment"], ["Multifamily", "Proptech", "Financing"], ["Investors", "Business Leaders"],
          "Beacon Capital Network", "A morning networking breakfast for real estate investors.", price=45, start="07:30", end="10:00"),
        E(19, "Automotive Mobility Summit", "summit", 69, 2, "Paris", "Paris Expo Porte de Versailles", "1 Place de la Porte de Versailles",
          ["Automotive", "Technology"], ["Electric Vehicles", "Autonomous Driving", "Charging"], ["Engineers", "Executives"],
          "Seine Mobility Group", "The future of electric and autonomous mobility.", price=480, currency="EUR"),
        E(20, "Hybrid Product Analytics Meetup", "meetup", 11, 1, "Toronto", "Community Hall Toronto", "151 Front St W",
          ["Data Science", "Product Management"], ["Funnels", "Retention", "Experimentation"], ["Product Managers", "Data Scientists"],
          "Northern Analytics Guild", "A hybrid meetup: attend in person or watch the stream.", fmt="hybrid", start="18:00", end="20:30"),
        E(21, "Nairobi Startup Investor Roundtable", "startup_event", 33, 1, "Nairobi", "iHub Nairobi", "Ngong Road",
          ["Startups", "Investment", "FinTech"], ["Seed Stage", "Mobile Payments", "Impact Investing"], ["Founders", "Investors"],
          "Savanna Ventures", "Closed-door roundtable connecting founders and regional investors.", start="13:00", end="17:00", image=False, org_desc=False),
        E(22, "Retail Tech Week (In Progress)", "conference", -1, 4, "New York", "Pier 36", "299 South St",
          ["Retail", "Technology", "E-commerce"], ["Omnichannel", "Store Analytics", "Payments"], ["Business Leaders", "Marketers"],
          "Harbor Expo Group", "Currently running: four days of retail technology sessions.", price=150),
        E(23, "Cloud Native Community Day", "conference", 24, 1, "Mumbai", "Jio World Convention Centre", "G Block, BKC",
          ["Cloud", "Software"], ["Kubernetes", "Observability", "Platform Engineering"], ["Developers", "Engineers", "CTOs"],
          "Deccan Cloud Community", "A community-run day of talks on cloud-native engineering.", coords=False, long_desc=False),
        E(24, "Manufacturing Innovation Forum (Postponed)", "conference", 90, 2, "Berlin", "Messe Berlin", "Messedamm 22",
          ["Manufacturing", "Business"], ["Industry 4.0", "Sustainability", "Digital Twins"], ["Business Leaders", "Engineers"],
          "Spree Product Community", "Postponed: new dates to be announced.", price=400, currency="EUR", status="postponed"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help=f"delete existing '{SOURCE}' events first")
    args = ap.parse_args()

    db = get_db()
    ensure_indexes(db)
    svc.ensure_default_categories(db)
    if args.reset:
        n = db["events"].delete_many({"source.name": SOURCE}).deleted_count
        print(f"removed {n} previous seed event(s)")

    counts: dict[str, int] = {}
    for raw, evt_id in seed_events():
        res = ingest_event(db, raw, source_name=SOURCE, auto_approve=True, use_ai=False, extra={"_id": evt_id})
        counts[res.action] = counts.get(res.action, 0) + 1
        if res.action in ("invalid", "flagged"):
            print(f"  ! {raw['title']}: {res.action} {res.errors or res.duplicate_of}")
    svc.refresh_statuses(db)
    total = db["events"].count_documents({"source.name": SOURCE})
    print(f"seed complete: {counts}  ({total} seed events in {db.name}.events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
