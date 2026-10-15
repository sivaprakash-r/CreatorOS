"""Two demo brands with deliberately different voices, used by the UI "seed demo" button, the
evaluation script and the tests. Different brand profiles must produce visibly different output."""

DEMO_BRANDS = [
    {
        "name": "Techsivam Labs",
        "description": "Solo technical founder writing about building AI products, Kubernetes and multi-cloud infra from Bangalore.",
        "example_brief": "a LinkedIn post about AI safety for engineering leaders",
        "example_platforms": ["linkedin", "x"],
        "samples": [
            {
                "platform": "linkedin",
                "text": (
                    "Most teams don't have a Kubernetes problem. They have a 'nobody owns the YAML' problem.\n\n"
                    "Last quarter I inherited a cluster with 41 Helm releases and zero owners. Here is what fixed it:\n\n"
                    "1. One CODEOWNERS line per namespace.\n2. A weekly 15-minute 'who deployed what' review.\n"
                    "3. Delete anything with no owner after 30 days.\n\n"
                    "Three months later: 17 releases, every one owned. The tooling never changed. The ownership did.\n\n"
                    "What is the one unowned thing in your cluster right now?"
                ),
            },
            {
                "platform": "linkedin",
                "text": (
                    "Unpopular opinion: your LLM gateway should be boring.\n\n"
                    "I built one in Go in two weeks. No fancy routing. Just: one key, a model allowlist, per-caller "
                    "budgets, and structured logs.\n\n"
                    "That boring box cut our Mesh spend by 38% in the first month because we could finally see which "
                    "agent was burning tokens.\n\n"
                    "Observability before cleverness. Every time."
                ),
            },
            {
                "platform": "linkedin",
                "text": (
                    "I shipped a feature on Friday. It broke on Saturday. Here is the trade-off I got wrong.\n\n"
                    "I optimised for a fast deploy (Cloud Run, no canary). The real risk was not the deploy — it was "
                    "the Cloud SQL connection pool, which hit its cap at 100 users.\n\n"
                    "Fix: PgBouncer in front, pool size 20, and a load test that runs before every release.\n\n"
                    "Lesson: measure the thing that actually falls over, not the thing that is easy to measure."
                ),
            },
            {
                "platform": "x",
                "text": "Kafka is not a queue. If you need a queue, use a queue. 80% of 'Kafka is hard' is really 'we wanted SQS'.",
            },
        ],
    },
    {
        "name": "Sunny Side Bakes",
        "description": "A cheerful neighbourhood bakery in Bangalore sharing recipes, behind-the-scenes and weekend specials.",
        "example_brief": "5 ways to make café-style coffee at home",
        "example_platforms": ["instagram"],
        "samples": [
            {
                "platform": "instagram",
                "text": (
                    "Good morning, sunshine! ☀️🥐 The croissants just came out and the whole street smells like butter.\n\n"
                    "This weekend's special: cardamom-rose danish 🌹 — only 40 of them, first come first served!\n\n"
                    "Tag the friend who needs a pastry today 💛\n\n#SunnySideBakes #BangaloreBakery #WeekendTreats #FreshlyBaked"
                ),
            },
            {
                "platform": "instagram",
                "text": (
                    "Behind the scenes at 4am 🕓✨ Priya is laminating 60 layers of dough while the rest of the city sleeps.\n\n"
                    "Fun fact: a croissant has 27 layers of butter. We counted. Twice. 😄\n\n"
                    "Come say hi after 7 — the first batch is always the best 🥐💛\n\n#BakeryLife #Croissant #SmallBusiness #Bangalore"
                ),
            },
            {
                "platform": "instagram",
                "text": (
                    "You asked, we baked! 🎉 The lemon-blueberry loaf is BACK for the monsoon 🍋🫐🌧️\n\n"
                    "Perfect with chai. Perfect with coffee. Perfect on its own (we tested extensively 😇).\n\n"
                    "Pre-order link in bio — save this post so you don't forget! 💛\n\n#SunnySideBakes #MonsoonBakes #LemonLoaf #BangaloreFoodies"
                ),
            },
        ],
    },
]
