"""
Comprehensive industry taxonomy for software engineering domains, skills, and languages.
Used to anchor LLM extraction to consistent slugs across the graph.

Structure:
  DOMAIN_TAXONOMY   — business & technical domains
  SKILL_TAXONOMY    — specific technical skills & practices
  LANGUAGE_TAXONOMY — programming languages, query languages, markup
  FRAMEWORK_TAXONOMY — frameworks, libraries, runtimes (mapped to their parent language)

All slugs are lowercase-hyphenated for consistent graph node naming.
"""

import re

# ─────────────────────────────────────────────────────────────────────────────
# DOMAINS  — what area of the product/system does this work touch?
# ─────────────────────────────────────────────────────────────────────────────
DOMAIN_TAXONOMY: dict[str, list[str]] = {
    "security-and-identity": [
        "authentication",  # login, sessions, tokens
        "authorisation",  # RBAC, ABAC, permissions
        "oauth-oidc",  # OAuth2, OIDC, SSO
        "mfa",  # multi-factor authentication
        "secret-management",  # Vault, AWS Secrets, env secrets
        "cryptography",  # encryption, hashing, signing
        "security-hardening",  # CVE fixes, OWASP, pen-test findings
        "audit-logging",  # security audit trails
        "compliance",  # GDPR, SOC2, HIPAA, PCI-DSS
        "zero-trust",  # zero-trust network access
    ],
    "payments-and-billing": [
        "payments",  # payment processing, PSP integration
        "billing",  # subscription billing, invoicing
        "checkout",  # cart, checkout flows
        "fraud-detection",  # fraud scoring, chargebacks
        "tax",  # tax calculation, VAT
        "revenue-recognition",  # accounting rules
        "payout",  # vendor/seller payouts
        "wallet",  # digital wallets, credits
        "pricing",  # pricing engine, discount rules
    ],
    "user-and-account-management": [
        "user-management",  # CRUD, profile management
        "onboarding",  # signup flows, activation
        "kyc",  # know-your-customer, identity verification
        "gdpr-data-rights",  # data deletion, exports
        "organisations",  # multi-tenant, orgs, teams
        "invitations",  # invite flows, referrals
        "preferences",  # user settings, feature flags per user
    ],
    "communication": [
        "email",  # transactional email, templates
        "sms",  # SMS messaging
        "push-notifications",  # mobile/web push
        "in-app-notifications",  # notification centre
        "webhooks",  # outbound webhooks
        "chat",  # real-time chat features
        "video-conferencing",  # video calls, WebRTC
        "notifications-infra",  # notification routing, delivery, retry
    ],
    "api-and-integrations": [
        "api-design",  # REST, resource design, versioning
        "graphql",  # GraphQL schema, resolvers
        "grpc",  # gRPC / protobuf
        "webhooks-inbound",  # receiving webhooks
        "sdk-development",  # client SDK libraries
        "third-party-integration",  # Stripe, Twilio, Salesforce, etc.
        "api-gateway",  # Kong, AWS API Gateway, nginx
        "api-versioning",  # v1/v2 strategy
        "rate-limiting",  # throttling, quota management
        "idempotency",  # idempotent API patterns
    ],
    "data-and-analytics": [
        "data-engineering",  # pipelines, ETL/ELT
        "data-warehousing",  # Snowflake, BigQuery, Redshift
        "business-intelligence",  # dashboards, reporting, Looker
        "analytics-events",  # event tracking, Segment, Mixpanel
        "data-modelling",  # dimensional modelling, dbt
        "real-time-analytics",  # streaming analytics, Flink
        "experimentation",  # A/B testing, feature experiments
        "product-analytics",  # funnels, retention, cohorts
        "data-quality",  # data validation, lineage, dq checks
        "data-governance",  # cataloguing, stewardship, PII tagging
    ],
    "machine-learning-and-ai": [
        "ml-training",  # model training pipelines
        "ml-inference",  # serving, prediction APIs
        "ml-ops",  # model versioning, drift, retraining
        "feature-engineering",  # feature stores, pipelines
        "nlp",  # NLP, text classification, NER
        "computer-vision",  # image/video ML
        "recommender-systems",  # recommendation engines
        "llm-integration",  # LLM APIs, prompt engineering
        "vector-search",  # embeddings, HNSW, ANN search
        "rag",  # retrieval-augmented generation
        "fine-tuning",  # model fine-tuning, LoRA
        "ai-safety",  # guardrails, output validation
        "knowledge-graphs",  # graph-based reasoning
    ],
    "search": [
        "search-relevance",  # ranking, scoring, BM25
        "search-infrastructure",  # Elasticsearch, OpenSearch, Solr
        "faceted-search",  # filters, aggregations
        "autocomplete",  # typeahead, suggestions
        "semantic-search",  # embedding-based search
        "search-analytics",  # click-through, search metrics
    ],
    "infrastructure-and-devops": [
        "cloud-infrastructure",  # AWS, GCP, Azure provisioning
        "containerisation",  # Docker, container builds
        "orchestration",  # Kubernetes, ECS, Nomad
        "infrastructure-as-code",  # Terraform, Pulumi, CDK
        "ci-cd",  # pipelines, build automation
        "deployment",  # release strategies, blue-green, canary
        "service-mesh",  # Istio, Linkerd, Envoy
        "networking",  # VPC, DNS, load balancing, firewalls
        "storage",  # S3, object storage, block storage
        "cdn",  # content delivery, edge caching
        "cost-optimisation",  # cloud cost, rightsizing
        "disaster-recovery",  # DR, RTO/RPO, backups
        "platform-engineering",  # internal developer platforms, golden paths
    ],
    "databases": [
        "relational-databases",  # PostgreSQL, MySQL, SQL Server
        "nosql",  # MongoDB, DynamoDB, Cassandra
        "graph-databases",  # Neo4j, Kuzu, TigerGraph
        "time-series-databases",  # InfluxDB, TimescaleDB, Prometheus
        "in-memory-databases",  # Redis, Memcached
        "search-databases",  # Elasticsearch as DB
        "database-migrations",  # schema migrations, Alembic, Flyway
        "database-replication",  # read replicas, CDC, binlog
        "database-sharding",  # horizontal partitioning
        "query-optimisation",  # indexes, query plans, EXPLAIN
        "database-admin",  # DBA tasks, backups, vacuuming
    ],
    "messaging-and-streaming": [
        "event-streaming",  # Kafka, Kinesis, Pulsar
        "message-queues",  # RabbitMQ, SQS, NATS
        "event-driven-architecture",  # event sourcing, pub/sub patterns
        "cqrs",  # command query responsibility segregation
        "outbox-pattern",  # transactional outbox
        "dead-letter-queues",  # DLQ handling, retry logic
        "stream-processing",  # Flink, Spark Streaming, consumer logic
    ],
    "observability": [
        "logging",  # structured logs, log aggregation
        "metrics",  # Prometheus, custom metrics
        "tracing",  # distributed tracing, OpenTelemetry
        "alerting",  # alert rules, PagerDuty, OpsGenie
        "dashboards",  # Grafana, Datadog dashboards
        "error-tracking",  # Sentry, Rollbar
        "apm",  # application performance monitoring
        "synthetic-monitoring",  # uptime checks, canary monitors
        "on-call",  # runbooks, incident response
        "slo-sli",  # SLO definitions, error budgets
    ],
    "performance": [
        "performance-optimisation",  # CPU, memory, I/O profiling
        "caching",  # cache strategies, invalidation
        "load-testing",  # k6, Locust, JMeter
        "scalability",  # horizontal scaling patterns
        "concurrency",  # async, threading, parallelism
        "latency-reduction",  # p99 improvements, critical path
        "database-performance",  # slow query, N+1, indexing
        "cdn-optimisation",  # edge caching, asset optimisation
    ],
    "testing-and-quality": [
        "unit-testing",  # isolated unit tests
        "integration-testing",  # service-level integration tests
        "e2e-testing",  # end-to-end browser/API tests
        "contract-testing",  # Pact, consumer-driven contracts
        "performance-testing",  # benchmarks, load tests
        "security-testing",  # SAST, DAST, pen testing automation
        "test-automation",  # test framework setup, CI integration
        "tdd",  # test-driven development practice
        "mutation-testing",  # code mutation coverage
        "snapshot-testing",  # UI snapshot tests
        "chaos-engineering",  # fault injection, resilience tests
    ],
    "architecture-and-design": [
        "system-design",  # high-level architecture decisions
        "microservices",  # service decomposition, contracts
        "monolith",  # monolithic architecture, modularisation
        "domain-driven-design",  # DDD, bounded contexts, aggregates
        "clean-architecture",  # hexagonal, ports-and-adapters
        "api-design",  # RESTful design principles
        "event-driven-architecture",  # event-first design
        "sagas",  # distributed transaction patterns
        "design-patterns",  # GoF, enterprise integration patterns
        "technical-debt",  # refactoring, debt reduction
        "refactoring",  # code restructuring
    ],
    "frontend": [
        "ui-development",  # component building, UI logic
        "state-management",  # Redux, Zustand, context API
        "routing",  # SPA routing, navigation
        "forms",  # form handling, validation
        "accessibility",  # a11y, WCAG, ARIA
        "internationalisation",  # i18n, l10n, translations
        "responsive-design",  # mobile-first, breakpoints
        "animations",  # transitions, motion design
        "micro-frontends",  # MFE architecture
        "browser-apis",  # Web APIs, PWA, service workers
        "web-performance",  # Core Web Vitals, bundle optimisation
        "design-systems",  # component libraries, tokens
        "css-architecture",  # BEM, CSS modules, Tailwind
    ],
    "mobile": [
        "ios-development",  # Swift, UIKit, SwiftUI
        "android-development",  # Kotlin, Jetpack Compose
        "cross-platform-mobile",  # React Native, Flutter
        "mobile-ci-cd",  # Fastlane, Xcode Cloud, Bitrise
        "app-store-deployment",  # App Store / Play Store releases
        "mobile-performance",  # memory, battery, startup time
        "offline-support",  # local storage, sync, conflict resolution
        "mobile-security",  # certificate pinning, keychain
        "push-notification-mobile",  # APNs, FCM
        "deep-linking",  # universal links, app links
    ],
    "developer-experience": [
        "dx-tooling",  # CLI tools, developer utilities
        "local-development",  # docker-compose, devcontainers, Makefile
        "documentation",  # API docs, runbooks, ADRs
        "code-generation",  # scaffolding, codegen, OpenAPI
        "developer-portals",  # Backstage, internal portals
        "onboarding-tooling",  # dev environment setup, scripts
        "monorepo",  # Nx, Turborepo, Bazel
        "package-management",  # npm, pip, poetry, dependency management
        "linting-formatting",  # ESLint, Prettier, Ruff, Black
        "git-workflow",  # branching strategies, hooks, git ops
    ],
    "product-and-growth": [
        "feature-flags",  # LaunchDarkly, Unleash, gradual rollout
        "experimentation",  # A/B tests, multivariate tests
        "growth-engineering",  # referral, viral loops, activation
        "seo",  # technical SEO, sitemaps, structured data
        "payment-conversion",  # checkout optimisation, cart recovery
        "personalisation",  # content/UX personalisation
        "gamification",  # points, badges, streaks
    ],
    "platform-and-tooling": [
        "internal-tooling",  # admin panels, internal dashboards
        "workflow-automation",  # Zapier-style automation, n8n
        "content-management",  # CMS integration, headless CMS
        "file-storage",  # S3, GCS, file upload/download
        "image-video-processing",  # media transcoding, resizing
        "pdf-generation",  # reports, invoices, doc generation
        "scheduling",  # cron jobs, task scheduling
        "batch-processing",  # bulk operations, large dataset jobs
        "geospatial",  # maps, location services, PostGIS
        "multi-tenancy",  # tenant isolation, data separation
    ],
}

# Flat list for LLM prompt injection
DOMAIN_SLUGS: list[str] = [slug for slugs in DOMAIN_TAXONOMY.values() for slug in slugs]


# ─────────────────────────────────────────────────────────────────────────────
# SKILLS  — specific technical capabilities demonstrated in the PR
# ─────────────────────────────────────────────────────────────────────────────
SKILL_TAXONOMY: dict[str, list[str]] = {
    "engineering-practices": [
        "tdd",
        "bdd",
        "pair-programming",
        "code-review",
        "refactoring",
        "technical-debt-reduction",
        "documentation-writing",
        "adr-authoring",  # Architecture Decision Records
        "design-review",
        "incident-response",
        "on-call-runbook",
        "postmortem-writing",
    ],
    "data-and-storage": [
        "database-migrations",
        "schema-design",
        "query-optimisation",
        "index-design",
        "database-sharding",
        "database-replication",
        "data-modelling",
        "data-pipeline-design",
        "etl-development",
        "data-quality-checks",
        "data-lineage",
        "cdc-implementation",  # change data capture
        "cache-design",
        "cache-invalidation",
        "redis-usage",
        "elasticsearch-usage",
        "vector-store-design",
    ],
    "api-and-integration": [
        "rest-api-design",
        "graphql-schema-design",
        "grpc-protobuf",
        "openapi-spec",
        "api-versioning",
        "idempotency-design",
        "rate-limiter-implementation",
        "webhook-design",
        "sdk-development",
        "third-party-api-integration",
        "oauth-implementation",
        "jwt-implementation",
    ],
    "infrastructure-and-devops": [
        "terraform-modules",
        "pulumi-stacks",
        "kubernetes-manifests",
        "helm-charts",
        "docker-image-optimisation",
        "github-actions-workflow",
        "gitlab-ci-pipeline",
        "jenkins-pipeline",
        "circle-ci-pipeline",
        "deployment-automation",
        "blue-green-deployment",
        "canary-release",
        "feature-flag-rollout",
        "infrastructure-cost-reduction",
        "auto-scaling-configuration",
        "networking-configuration",
        "dns-management",
        "ssl-tls-configuration",
        "secret-rotation",
        "backup-automation",
    ],
    "observability-and-reliability": [
        "logging-implementation",
        "metrics-instrumentation",
        "distributed-tracing",
        "alert-rule-design",
        "slo-definition",
        "error-budget-policy",
        "synthetic-monitoring",
        "chaos-experiment",
        "load-testing",
        "performance-profiling",
        "memory-leak-fix",
        "cpu-optimisation",
        "latency-reduction",
    ],
    "security": [
        "vulnerability-patching",
        "dependency-audit",
        "sast-integration",
        "dast-integration",
        "penetration-test-fix",
        "encryption-implementation",
        "secret-scanning",
        "access-control-implementation",
        "audit-log-implementation",
        "gdpr-compliance-implementation",
        "pci-dss-compliance",
        "certificate-management",
        "firewall-rules",
    ],
    "testing": [
        "unit-test-writing",
        "integration-test-writing",
        "e2e-test-writing",
        "test-fixture-design",
        "mock-stub-design",
        "contract-test-writing",
        "snapshot-test-writing",
        "performance-test-writing",
        "test-coverage-improvement",
        "flaky-test-fix",
        "test-parallelisation",
    ],
    "architecture": [
        "service-decomposition",
        "event-sourcing-implementation",
        "saga-pattern",
        "outbox-pattern",
        "cqrs-implementation",
        "strangler-fig-migration",
        "domain-modelling",
        "bounded-context-design",
        "hexagonal-architecture",
        "dependency-inversion",
        "monolith-to-microservices",
        "api-gateway-setup",
        "service-mesh-configuration",
    ],
    "ml-and-ai": [
        "model-training-pipeline",
        "model-serving",
        "feature-store-integration",
        "prompt-engineering",
        "rag-pipeline",
        "embedding-pipeline",
        "ml-experiment-tracking",
        "model-evaluation",
        "fine-tuning",
        "llm-integration",
        "vector-index-build",
        "knowledge-graph-build",
        "ml-monitoring",
    ],
    "frontend-and-mobile": [
        "component-library",
        "design-system-implementation",
        "state-management-refactor",
        "web-performance-optimisation",
        "accessibility-remediation",
        "i18n-implementation",
        "responsive-layout",
        "animation-implementation",
        "pwa-implementation",
        "react-native-bridge",
        "flutter-widget",
        "mobile-deeplink",
        "push-notification-implementation",
    ],
    "developer-experience": [
        "cli-tool-development",
        "codegen-tooling",
        "dev-environment-setup",
        "monorepo-configuration",
        "linting-configuration",
        "formatting-automation",
        "git-hooks-setup",
        "package-publish",
        "dependency-upgrade",
        "api-doc-generation",
        "internal-dashboard",
    ],
}

SKILL_SLUGS: list[str] = [slug for slugs in SKILL_TAXONOMY.values() for slug in slugs]


# ─────────────────────────────────────────────────────────────────────────────
# LANGUAGES  — inferred primarily from file extensions
# ─────────────────────────────────────────────────────────────────────────────
LANGUAGE_TAXONOMY: dict[str, list[str]] = {
    "systems": ["Rust", "C", "C++", "Zig", "Go"],
    "backend-general": [
        "Python",
        "Java",
        "Kotlin",
        "Scala",
        "Ruby",
        "PHP",
        "C#",
        "Elixir",
        "Erlang",
        "Haskell",
        "Clojure",
        "F#",
        "Groovy",
        "Perl",
        "Lua",
    ],
    "frontend": ["JavaScript", "TypeScript", "Dart"],
    "mobile": ["Swift", "Objective-C", "Kotlin"],
    "data-and-ml": ["R", "Julia", "MATLAB", "Jupyter Notebook"],
    "query-and-schema": ["SQL", "GraphQL", "SPARQL", "Cypher", "HQL"],
    "infrastructure": [
        "HCL",
        "Terraform",
        "Pulumi",
        "Dockerfile",
        "Shell",
        "Bash",
        "PowerShell",
        "Makefile",
    ],
    "markup-and-config": [
        "HTML",
        "CSS",
        "SCSS",
        "LESS",
        "YAML",
        "TOML",
        "JSON",
        "XML",
        "Markdown",
        "LaTeX",
        "Jinja2",
    ],
    "mobile-cross-platform": ["Dart"],  # Flutter
    "query-engines": ["Presto", "Spark SQL", "BigQuery SQL", "dbt"],
}

# Extension → Language mapping (for file-based detection)
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".pyw": "Python",
    ".pyx": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".rb": "Ruby",
    ".rake": "Ruby",
    ".gemspec": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".c": "C",
    ".h": "C",
    ".hpp": "C++",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".clj": "Clojure",
    ".cljs": "Clojure",
    ".fs": "F#",
    ".fsx": "F#",
    ".r": "R",
    ".R": "R",
    ".jl": "Julia",
    ".lua": "Lua",
    ".groovy": "Groovy",
    ".zig": "Zig",
    ".dart": "Dart",
    ".sql": "SQL",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".sh": "Shell",
    ".bash": "Bash",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".tf": "Terraform",
    ".tfvars": "Terraform",
    ".hcl": "HCL",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".xml": "XML",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SCSS",
    ".less": "LESS",
    ".md": "Markdown",
    ".mdx": "Markdown",
    ".tex": "LaTeX",
    ".dockerfile": "Dockerfile",
    ".ipynb": "Jupyter Notebook",
    ".proto": "Protobuf",
    ".j2": "Jinja2",
    ".jinja": "Jinja2",
    ".makefile": "Makefile",
}

LANGUAGE_SLUGS: list[str] = list(
    {lang for langs in LANGUAGE_TAXONOMY.values() for lang in langs}
)


# ─────────────────────────────────────────────────────────────────────────────
# FRAMEWORKS  — mapped to parent language for enriched author profiles
# ─────────────────────────────────────────────────────────────────────────────
FRAMEWORK_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "Python": {
        "web": ["FastAPI", "Django", "Flask", "Starlette", "Litestar"],
        "data": ["Pandas", "Polars", "NumPy", "Dask", "PySpark"],
        "ml": [
            "PyTorch",
            "TensorFlow",
            "Scikit-learn",
            "Hugging Face",
            "LangChain",
            "LlamaIndex",
            "XGBoost",
            "LightGBM",
        ],
        "testing": ["pytest", "unittest", "Hypothesis"],
        "tasks": ["Celery", "Dramatiq", "Prefect", "Airflow", "Luigi"],
        "orm": ["SQLAlchemy", "Tortoise ORM", "Django ORM", "Peewee"],
        "infra": ["Pulumi", "boto3", "CDK"],
    },
    "TypeScript": {
        "web-frontend": [
            "React",
            "Next.js",
            "Remix",
            "Astro",
            "Vue",
            "Nuxt",
            "Angular",
            "SvelteKit",
            "Svelte",
        ],
        "web-backend": ["NestJS", "Express", "Fastify", "Hono", "tRPC"],
        "testing": ["Jest", "Vitest", "Playwright", "Cypress", "Testing Library"],
        "state": ["Redux", "Zustand", "Jotai", "MobX", "XState"],
        "build": ["Vite", "Webpack", "esbuild", "Turbopack"],
        "orm": ["Prisma", "Drizzle", "TypeORM", "Kysely"],
    },
    "JavaScript": {
        "runtime": ["Node.js", "Deno", "Bun"],
        "web-frontend": ["React", "Vue", "Angular", "Svelte"],
    },
    "Go": {
        "web": ["Gin", "Echo", "Fiber", "Chi", "gRPC-Go"],
        "infra": ["Terraform SDK", "Operator SDK"],
    },
    "Java": {
        "web": ["Spring Boot", "Spring MVC", "Quarkus", "Micronaut", "Vert.x"],
        "testing": ["JUnit", "Mockito", "TestContainers"],
        "data": ["Apache Spark", "Flink", "Kafka Streams"],
    },
    "Kotlin": {
        "android": ["Jetpack Compose", "Android SDK", "Ktor (client)"],
        "backend": ["Ktor", "Spring Boot", "Exposed"],
    },
    "Swift": {
        "ios": ["SwiftUI", "UIKit", "Combine", "XCTest"],
    },
    "Dart": {
        "mobile": ["Flutter"],
    },
    "Ruby": {
        "web": ["Rails", "Sinatra", "Hanami"],
        "testing": ["RSpec", "Minitest"],
    },
    "Rust": {
        "web": ["Axum", "Actix Web", "Warp", "Rocket"],
        "async": ["Tokio", "async-std"],
    },
    "Scala": {
        "data": ["Apache Spark", "Akka", "ZIO", "Cats Effect"],
    },
    "Elixir": {
        "web": ["Phoenix", "LiveView"],
        "jobs": ["Oban"],
    },
    "C#": {
        "web": [".NET", "ASP.NET Core", "Blazor", "MAUI"],
        "testing": ["xUnit", "NUnit", "Moq"],
    },
    "PHP": {
        "web": ["Laravel", "Symfony", "WordPress"],
    },
    "Shell": {
        "tooling": ["Bash", "zsh", "fish"],
    },
}

# Flat slug list for LLM prompt
FRAMEWORK_SLUGS: list[str] = [
    fw
    for lang_cats in FRAMEWORK_TAXONOMY.values()
    for fws in lang_cats.values()
    for fw in fws
]


# ─────────────────────────────────────────────────────────────────────────────
# TOOLS  — specific tools / platforms (for enriched skill graph)
# ─────────────────────────────────────────────────────────────────────────────
TOOL_TAXONOMY: dict[str, list[str]] = {
    "databases": [
        "PostgreSQL",
        "MySQL",
        "SQLite",
        "Oracle",
        "SQL Server",
        "MongoDB",
        "DynamoDB",
        "Cassandra",
        "CouchDB",
        "RethinkDB",
        "Redis",
        "Memcached",
        "Dragonfly",
        "Elasticsearch",
        "OpenSearch",
        "Solr",
        "Neo4j",
        "Kuzu",
        "TigerGraph",
        "Neptune",
        "InfluxDB",
        "TimescaleDB",
        "QuestDB",
        "Snowflake",
        "BigQuery",
        "Redshift",
        "Databricks",
        "ClickHouse",
        "CockroachDB",
        "YugabyteDB",
        "PlanetScale",
        "Neon",
        "Supabase",
        "Pinecone",
        "Weaviate",
        "Qdrant",
        "Milvus",
        "Chroma",
    ],
    "messaging": [
        "Apache Kafka",
        "RabbitMQ",
        "AWS SQS",
        "AWS SNS",
        "NATS",
        "Apache Pulsar",
        "Google Pub/Sub",
        "Azure Service Bus",
        "Redis Streams",
        "Kinesis",
    ],
    "cloud": [
        "AWS",
        "GCP",
        "Azure",
        "Cloudflare",
        "Vercel",
        "Netlify",
        "DigitalOcean",
        "Hetzner",
        "Fly.io",
        "Render",
    ],
    "observability": [
        "Datadog",
        "Grafana",
        "Prometheus",
        "Loki",
        "Tempo",
        "OpenTelemetry",
        "Jaeger",
        "Zipkin",
        "New Relic",
        "Dynatrace",
        "Sentry",
        "Rollbar",
        "Bugsnag",
        "Honeycomb",
        "PagerDuty",
        "OpsGenie",
        "VictorOps",
    ],
    "ci-cd": [
        "GitHub Actions",
        "GitLab CI",
        "CircleCI",
        "Jenkins",
        "Travis CI",
        "Buildkite",
        "TeamCity",
        "ArgoCD",
        "Flux",
        "Spinnaker",
        "Tekton",
        "Drone CI",
        "Fastlane",
    ],
    "infra-tools": [
        "Terraform",
        "Pulumi",
        "Ansible",
        "Chef",
        "Puppet",
        "SaltStack",
        "Kubernetes",
        "Helm",
        "Kustomize",
        "Docker",
        "Podman",
        "Istio",
        "Linkerd",
        "Envoy",
        "Nginx",
        "HAProxy",
        "Traefik",
        "Vault",
        "Consul",
        "etcd",
    ],
    "data-tools": [
        "Apache Spark",
        "Apache Flink",
        "dbt",
        "Airbyte",
        "Fivetran",
        "Airflow",
        "Prefect",
        "Dagster",
        "Luigi",
        "Mage",
        "Kafka Connect",
        "Debezium",
        "Stitch",
        "Looker",
        "Metabase",
        "Superset",
        "Tableau",
        "Power BI",
        "Redash",
        "Mode",
        "Hex",
    ],
    "ml-tools": [
        "MLflow",
        "Weights & Biases",
        "DVC",
        "Kubeflow",
        "SageMaker",
        "Vertex AI",
        "Azure ML",
        "ClearML",
        "Neptune.ai",
        "LangChain",
        "LlamaIndex",
        "Semantic Kernel",
        "Hugging Face",
        "ONNX",
        "TensorRT",
        "Triton",
    ],
    "testing-tools": [
        "Selenium",
        "Playwright",
        "Cypress",
        "Puppeteer",
        "TestCafe",
        "k6",
        "Locust",
        "JMeter",
        "Gatling",
        "Postman",
        "Insomnia",
        "Bruno",
        "SonarQube",
        "Snyk",
        "Dependabot",
        "Renovate",
    ],
    "communication": [
        "Twilio",
        "SendGrid",
        "Mailgun",
        "Postmark",
        "Amazon SES",
        "Firebase FCM",
        "APNs",
        "OneSignal",
        "Vonage",
        "Plivo",
        "MessageBird",
    ],
    "payments": [
        "Stripe",
        "PayPal",
        "Braintree",
        "Adyen",
        "Square",
        "Razorpay",
        "Paddle",
        "Chargebee",
        "Zuora",
    ],
    "auth-providers": [
        "Auth0",
        "Okta",
        "Keycloak",
        "Cognito",
        "Firebase Auth",
        "Supabase Auth",
        "Clerk",
        "WorkOS",
        "FusionAuth",
    ],
    "feature-flags": [
        "LaunchDarkly",
        "Unleash",
        "Flagsmith",
        "GrowthBook",
        "Split.io",
        "Statsig",
        "Optimizely",
    ],
    "cms-and-content": [
        "Contentful",
        "Sanity",
        "Strapi",
        "Ghost",
        "WordPress",
        "Prismic",
        "DatoCMS",
        "Storyblok",
    ],
    "search-tools": [
        "Elasticsearch",
        "OpenSearch",
        "Typesense",
        "Meilisearch",
        "Algolia",
        "Solr",
    ],
}

TOOL_SLUGS: list[str] = [tool for tools in TOOL_TAXONOMY.values() for tool in tools]


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT HELPERS  — pre-formatted strings for LLM system prompts
# ─────────────────────────────────────────────────────────────────────────────


def get_domain_prompt_block() -> str:
    lines = ["Valid domain slugs (map to the closest match, or use the exact slug):"]
    for category, slugs in DOMAIN_TAXONOMY.items():
        lines.append(f"  [{category}]: {', '.join(slugs)}")
    return "\n".join(lines)


def get_skill_prompt_block() -> str:
    lines = ["Valid skill slugs:"]
    for category, slugs in SKILL_TAXONOMY.items():
        lines.append(f"  [{category}]: {', '.join(slugs)}")
    return "\n".join(lines)


def get_language_prompt_block() -> str:
    return f"Valid programming languages: {', '.join(LANGUAGE_SLUGS)}"


def get_framework_prompt_block() -> str:
    return f"Valid frameworks/libraries: {', '.join(FRAMEWORK_SLUGS)}"


def get_tool_prompt_block() -> str:
    return f"Valid tools/platforms: {', '.join(TOOL_SLUGS)}"


def get_full_taxonomy_prompt() -> str:
    """Returns the complete taxonomy block to inject into the LLM extraction prompt."""
    return "\n\n".join(
        [
            get_domain_prompt_block(),
            get_skill_prompt_block(),
            get_language_prompt_block(),
            get_framework_prompt_block(),
            get_tool_prompt_block(),
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Regex pattern tables  (compiled once at module level)
# ─────────────────────────────────────────────────────────────────────────────
_I = re.IGNORECASE

# Domain patterns: list[tuple[re.Pattern, str]]
DOMAIN_PATTERNS: list[tuple[re.Pattern, str]] = [
    # security-and-identity
    (
        re.compile(
            r"\b(?:auth|oauth|jwt|session|token|login|password|sso|saml|mfa)\b", _I
        ),
        "authentication",
    ),
    (
        re.compile(r"\b(?:authoriz|rbac|abac|permission|access[.\s_-]control)\b", _I),
        "authorisation",
    ),
    (
        re.compile(
            r"\b(?:secret|vault|aws[.\s_-]secrets|keystore|credential[.\s_-]manag)", _I
        ),
        "secret-management",
    ),
    (
        re.compile(r"\b(?:encrypt|decrypt|hash|signing|tls|ssl|cert|pki)\b", _I),
        "cryptography",
    ),
    (
        re.compile(
            r"\b(?:vuln|cve|owasp|security[.\s_-]fix|sast|dast|pen[.\s_-]test)\b", _I
        ),
        "security-hardening",
    ),
    (
        re.compile(
            r"\b(?:gdpr|ccpa|hipaa|pci[.\s_-]dss|soc2|compliance|data[.\s_-]protection)\b",
            _I,
        ),
        "compliance",
    ),
    # payments-and-billing
    (
        re.compile(
            r"\b(?:payment|stripe|braintree|adyen|checkout|billing|invoice)\b", _I
        ),
        "payments",
    ),
    (
        re.compile(r"\b(?:fraud|risk[.\s_-]scor|dispute|chargeback)\b", _I),
        "fraud-detection",
    ),
    # communication
    (re.compile(r"\b(?:email|smtp|sendgrid|mailgun|ses|postmark)\b", _I), "email"),
    (re.compile(r"\b(?:sms|twilio|vonage|text[.\s_-]messag)\b", _I), "sms"),
    (
        re.compile(
            r"\b(?:push[.\s_-]notif|fcm|apns|onesignal|firebase[.\s_-]messaging)\b", _I
        ),
        "push-notifications",
    ),
    (re.compile(r"\bwebhook\b", _I), "webhooks"),
    # api-and-integrations
    (re.compile(r"\b(?:graphql|resolver|mutation|apollo)\b", _I), "graphql"),
    (re.compile(r"\b(?:grpc|protobuf|proto\b|thrift)\b", _I), "grpc"),
    (re.compile(r"\b(?:rate[.\s_-]limit|throttl|quota)\b", _I), "rate-limiting"),
    (re.compile(r"\bidempoten", _I), "idempotency"),
    # data-and-analytics
    (
        re.compile(r"\b(?:etl|elt|pipeline|airflow|prefect|dagster)\b", _I),
        "data-engineering",
    ),
    (
        re.compile(r"\b(?:snowflake|bigquery|redshift|databricks|clickhouse)\b", _I),
        "data-warehousing",
    ),
    (
        re.compile(
            r"\b(?:dashboard|looker|metabase|superset|tableau|power[.\s_-]bi)\b", _I
        ),
        "business-intelligence",
    ),
    (
        re.compile(
            r"\b(?:a/b[.\s_-]test|experiment|feature[.\s_-]flag|split[.\s_-]test)\b", _I
        ),
        "experimentation",
    ),
    # machine-learning-and-ai
    (
        re.compile(
            r"\b(?:ml[.\s_-]train|model[.\s_-]train|pytorch|tensorflow|sklearn)\b", _I
        ),
        "ml-training",
    ),
    (
        re.compile(
            r"\b(?:ml[.\s_-]infer|model[.\s_-]serv|prediction|inference[.\s_-]endpoint)\b",
            _I,
        ),
        "ml-inference",
    ),
    (
        re.compile(
            r"\b(?:mlflow|mlops|model[.\s_-]registr|drift|kubeflow|sagemaker)\b", _I
        ),
        "ml-ops",
    ),
    (
        re.compile(r"\b(?:llm|gpt|claude|openai|anthropic|langchain|llamaindex)\b", _I),
        "llm-integration",
    ),
    (
        re.compile(
            r"\b(?:embedding|vector[.\s_-]store|hnsw|faiss|pinecone|weaviate|qdrant)\b",
            _I,
        ),
        "vector-search",
    ),
    (re.compile(r"\brag\b|retrieval[.\s_-]augmented", _I), "rag"),
    (
        re.compile(
            r"\bnlp\b|text[.\s_-]classif|named[.\s_-]entity|sentiment|transformers\b",
            _I,
        ),
        "nlp",
    ),
    (
        re.compile(r"\b(?:knowledge[.\s_-]graph|graphrag|neo4j)\b", _I),
        "knowledge-graphs",
    ),
    # infrastructure-and-devops
    (
        re.compile(
            r"\b(?:terraform|pulumi|cdk\b|infrastructure[.\s_-]as[.\s_-]code|iac\b)", _I
        ),
        "infrastructure-as-code",
    ),
    (re.compile(r"\b(?:docker|container|dockerfile|podman)\b", _I), "containerisation"),
    (
        re.compile(r"\b(?:kubernetes|k8s\b|helm\b|kustomize|eks|gke|aks)\b", _I),
        "orchestration",
    ),
    (
        re.compile(
            r"\b(?:github[.\s_-]action|gitlab[.\s_-]ci|circle[.\s_-]?ci|jenkins|ci[.\s_-]cd)\b",
            _I,
        ),
        "ci-cd",
    ),
    (
        re.compile(r"\b(?:deploy|release|rollout|blue[.\s_-]green|canary)\b", _I),
        "deployment",
    ),
    (
        re.compile(r"\b(?:service[.\s_-]mesh|istio|linkerd|envoy\b)\b", _I),
        "service-mesh",
    ),
    # databases
    (
        re.compile(r"\b(?:postgres|mysql|sqlite|rds\b|aurora\b)\b", _I),
        "relational-databases",
    ),
    (
        re.compile(r"\b(?:mongo|dynamo|cassandra|nosql|document[.\s_-]store)\b", _I),
        "nosql",
    ),
    (
        re.compile(r"\b(?:redis|memcache|in[.\s_-]memory|dragonfly)\b", _I),
        "in-memory-databases",
    ),
    (
        re.compile(r"\b(?:migrat|alembic|flyway|liquibase|schema[.\s_-]change)\b", _I),
        "database-migrations",
    ),
    (
        re.compile(
            r"\b(?:query[.\s_-]optim|slow[.\s_-]query|n\+1|index\b|explain[.\s_-]plan)\b",
            _I,
        ),
        "query-optimisation",
    ),
    # messaging-and-streaming
    (
        re.compile(r"\b(?:kafka|kinesis|pulsar|event[.\s_-]stream)\b", _I),
        "event-streaming",
    ),
    (
        re.compile(
            r"\b(?:rabbitmq|sqs\b|nats\b|message[.\s_-]queue|pub[.\s_-]sub)\b", _I
        ),
        "message-queues",
    ),
    (
        re.compile(
            r"\b(?:event[.\s_-]sourc|event[.\s_-]driven|event[.\s_-]store)\b", _I
        ),
        "event-driven-architecture",
    ),
    (re.compile(r"\bcqrs\b", _I), "cqrs"),
    (
        re.compile(r"\b(?:outbox[.\s_-]pattern|transactional[.\s_-]outbox)\b", _I),
        "outbox-pattern",
    ),
    # observability
    (
        re.compile(r"\b(?:log|loki\b|fluentd|logstash|structured[.\s_-]log)\b", _I),
        "logging",
    ),
    (re.compile(r"\b(?:prometheus|metric|gauge|counter|histogram)\b", _I), "metrics"),
    (re.compile(r"\b(?:tracing|opentelemetry|otel\b|jaeger|zipkin)\b", _I), "tracing"),
    (re.compile(r"\b(?:alert|pagerduty|opsgenie)\b", _I), "alerting"),
    (
        re.compile(r"\b(?:grafana|datadog|new[.\s_-]relic|dynatrace)\b", _I),
        "dashboards",
    ),
    (
        re.compile(r"\b(?:sentry|rollbar|bugsnag|error[.\s_-]track)\b", _I),
        "error-tracking",
    ),
    (
        re.compile(r"\b(?:slo\b|sli\b|error[.\s_-]budget|service[.\s_-]level)\b", _I),
        "slo-sli",
    ),
    # performance
    (
        re.compile(r"\b(?:perf|optim|benchmark|profil|latency|throughput|p99)\b", _I),
        "performance-optimisation",
    ),
    (re.compile(r"\b(?:cach|cache[.\s_-]strategy|ttl\b|invalidat)\b", _I), "caching"),
    (
        re.compile(r"\b(?:load[.\s_-]test|stress[.\s_-]test|k6\b|locust|jmeter)\b", _I),
        "load-testing",
    ),
    # testing-and-quality
    (
        re.compile(r"\b(?:unit[.\s_-]test|pytest|jest\b|vitest|junit|rspec)\b", _I),
        "unit-testing",
    ),
    (
        re.compile(r"\b(?:integration[.\s_-]test|testcontainer|supertest)\b", _I),
        "integration-testing",
    ),
    (
        re.compile(
            r"\b(?:e2e|end[.\s_-]to[.\s_-]end|playwright|cypress|selenium)\b", _I
        ),
        "e2e-testing",
    ),
    (
        re.compile(r"\b(?:chaos|fault[.\s_-]inject|resilience[.\s_-]test)\b", _I),
        "chaos-engineering",
    ),
    # frontend
    (
        re.compile(r"\b(?:react\b|vue\b|angular\b|svelte|next\.js|frontend)\b", _I),
        "ui-development",
    ),
    (
        re.compile(r"\b(?:redux|zustand|jotai|mobx|state[.\s_-]manag)\b", _I),
        "state-management",
    ),
    (
        re.compile(r"\b(?:access|a11y\b|wcag|aria\b|screen[.\s_-]reader)\b", _I),
        "accessibility",
    ),
    (
        re.compile(r"\b(?:i18n\b|l10n\b|internationaliz|localiz|translat)\b", _I),
        "internationalisation",
    ),
    (
        re.compile(
            r"\b(?:core[.\s_-]web[.\s_-]vital|bundle[.\s_-]optim|web[.\s_-]perform|lighthouse)\b",
            _I,
        ),
        "web-performance",
    ),
    (
        re.compile(r"\b(?:design[.\s_-]system|component[.\s_-]librar|storybook)\b", _I),
        "design-systems",
    ),
    # mobile
    (re.compile(r"\b(?:swiftui|uikit|ios\b|xcode)\b", _I), "ios-development"),
    (
        re.compile(r"\b(?:jetpack[.\s_-]compose|android\b|kotlin[.\s_-]android)\b", _I),
        "android-development",
    ),
    (
        re.compile(
            r"\b(?:react[.\s_-]native|flutter\b|expo\b|cross[.\s_-]platform[.\s_-]mobile)\b",
            _I,
        ),
        "cross-platform-mobile",
    ),
    # architecture-and-design
    (re.compile(r"\b(?:microservice|service[.\s_-]decomp)\b", _I), "microservices"),
    (
        re.compile(
            r"\b(?:domain[.\s_-]driven|ddd\b|bounded[.\s_-]context|aggregate\b)\b", _I
        ),
        "domain-driven-design",
    ),
    (
        re.compile(
            r"\b(?:hexagonal|ports[.\s_-]and[.\s_-]adapter|clean[.\s_-]arch)\b", _I
        ),
        "clean-architecture",
    ),
    (
        re.compile(r"\b(?:saga[.\s_-]pattern|distributed[.\s_-]transaction)\b", _I),
        "sagas",
    ),
    (
        re.compile(
            r"\b(?:refactor|restructur|clean[.\s_-]up|technical[.\s_-]debt)\b", _I
        ),
        "refactoring",
    ),
    # product-and-growth
    (
        re.compile(r"\b(?:feature[.\s_-]flag|launchdarkly|unleash|flagsmith)\b", _I),
        "feature-flags",
    ),
    # developer-experience
    (
        re.compile(r"\b(?:eslint|prettier|ruff\b|black\b|flake8|pylint|lint)\b", _I),
        "linting-formatting",
    ),
    (re.compile(r"\b(?:monorepo|nx\b|turborepo|bazel\b)\b", _I), "monorepo"),
]

# Skill patterns: list[tuple[re.Pattern, str]]
SKILL_PATTERNS: list[tuple[re.Pattern, str]] = [
    # data-and-storage
    (
        re.compile(r"\b(?:migrat|alembic|flyway|liquibase|schema[.\s_-]change)\b", _I),
        "database-migrations",
    ),
    (
        re.compile(
            r"\b(?:schema[.\s_-]design|erd\b|data[.\s_-]model|table[.\s_-]design)\b", _I
        ),
        "schema-design",
    ),
    (
        re.compile(r"\b(?:query[.\s_-]optim|n\+1|slow[.\s_-]query|explain\b)\b", _I),
        "query-optimisation",
    ),
    (
        re.compile(
            r"\b(?:index[.\s_-]design|composite[.\s_-]index|partial[.\s_-]index)\b", _I
        ),
        "index-design",
    ),
    (
        re.compile(
            r"\b(?:cache[.\s_-]design|cache[.\s_-]strategy|invalidat|cache[.\s_-]warm)\b",
            _I,
        ),
        "cache-design",
    ),
    # infrastructure-and-devops
    (
        re.compile(r"\b(?:terraform[.\s_-]module|reusable[.\s_-]infra)\b", _I),
        "terraform-modules",
    ),
    (
        re.compile(r"\b(?:helm[.\s_-]chart|helm[.\s_-]template|chart\.yaml)\b", _I),
        "helm-charts",
    ),
    (
        re.compile(
            r"\b(?:docker[.\s_-]optim|multi[.\s_-]stage[.\s_-]build|layer[.\s_-]optim)\b",
            _I,
        ),
        "docker-image-optimisation",
    ),
    (
        re.compile(r"\b(?:github[.\s_-]action|workflow\.yml|\.github/workflows)\b", _I),
        "github-actions-workflow",
    ),
    (re.compile(r"\b(?:gitlab[.\s_-]?ci|\.gitlab-ci)\b", _I), "gitlab-ci-pipeline"),
    (
        re.compile(r"\b(?:blue[.\s_-]green|zero[.\s_-]downtime[.\s_-]deploy)\b", _I),
        "blue-green-deployment",
    ),
    (
        re.compile(r"\b(?:canary[.\s_-]releas|gradual[.\s_-]rollout)\b", _I),
        "canary-release",
    ),
    (
        re.compile(r"\b(?:infra[.\s_-]cost|cost[.\s_-]reduc|rightsiz)\b", _I),
        "infrastructure-cost-reduction",
    ),
    # observability-and-reliability
    (
        re.compile(
            r"\b(?:structured[.\s_-]log|log[.\s_-]format|correlation[.\s_-]id)\b", _I
        ),
        "logging-implementation",
    ),
    (
        re.compile(r"\b(?:custom[.\s_-]metric|prometheus[.\s_-]exporter)\b", _I),
        "metrics-instrumentation",
    ),
    (
        re.compile(r"\b(?:distributed[.\s_-]trac|span\b|trace[.\s_-]context)\b", _I),
        "distributed-tracing",
    ),
    (
        re.compile(r"\b(?:slo[.\s_-]defin|error[.\s_-]budget|sli[.\s_-]defin)\b", _I),
        "slo-definition",
    ),
    # api-and-integration
    (
        re.compile(
            r"\b(?:rest[.\s_-]api[.\s_-]design|resource[.\s_-]design|api[.\s_-]contract)\b",
            _I,
        ),
        "rest-api-design",
    ),
    (
        re.compile(
            r"\b(?:graphql[.\s_-]schema|resolver[.\s_-]design|type[.\s_-]def)\b", _I
        ),
        "graphql-schema-design",
    ),
    (re.compile(r"\b(?:grpc|protobuf|proto[.\s_-]defin)\b", _I), "grpc-protobuf"),
    (
        re.compile(r"\b(?:openapi|swagger[.\s_-]spec|api[.\s_-]spec)\b", _I),
        "openapi-spec",
    ),
    (
        re.compile(
            r"\b(?:rate[.\s_-]limiter|token[.\s_-]bucket|leaky[.\s_-]bucket)\b", _I
        ),
        "rate-limiter-implementation",
    ),
    (re.compile(r"\b(?:idempoten|idempotency[.\s_-]key)\b", _I), "idempotency-design"),
    (
        re.compile(
            r"\b(?:webhook[.\s_-]design|webhook[.\s_-]verif|webhook[.\s_-]retry)\b", _I
        ),
        "webhook-design",
    ),
    # testing
    (
        re.compile(
            r"\b(?:unit[.\s_-]test[.\s_-]writ|add.*test|test[.\s_-]suite)\b", _I
        ),
        "unit-test-writing",
    ),
    (
        re.compile(
            r"\b(?:integration[.\s_-]test[.\s_-]writ|testcontainer|docker[.\s_-]test)\b",
            _I,
        ),
        "integration-test-writing",
    ),
    (
        re.compile(
            r"\b(?:e2e[.\s_-]test|playwright[.\s_-]test|cypress[.\s_-]spec)\b", _I
        ),
        "e2e-test-writing",
    ),
    (
        re.compile(r"\b(?:test[.\s_-]coverage|coverage[.\s_-]increas)\b", _I),
        "test-coverage-improvement",
    ),
    (re.compile(r"\b(?:flaky[.\s_-]test|test[.\s_-]stabil)\b", _I), "flaky-test-fix"),
    # ml-and-ai
    (
        re.compile(
            r"\b(?:prompt[.\s_-]engineer|system[.\s_-]prompt|few[.\s_-]shot|chain[.\s_-]of[.\s_-]thought)\b",
            _I,
        ),
        "prompt-engineering",
    ),
    (
        re.compile(r"\b(?:rag[.\s_-]pipeline|retrieval[.\s_-]pipeline|chunking)\b", _I),
        "rag-pipeline",
    ),
    (
        re.compile(r"\b(?:vector[.\s_-]index|hnsw[.\s_-]index|ann[.\s_-]index)\b", _I),
        "vector-index-build",
    ),
    (
        re.compile(r"\b(?:model[.\s_-]drift|data[.\s_-]drift|ml[.\s_-]monitor)\b", _I),
        "ml-monitoring",
    ),
    # engineering-practices
    (
        re.compile(
            r"\b(?:refactor|restructur|clean[.\s_-]up|extract[.\s_-]method)\b", _I
        ),
        "refactoring",
    ),
    # security
    (
        re.compile(
            r"\b(?:access[.\s_-]control[.\s_-]impl|rbac[.\s_-]impl|permission[.\s_-]impl)\b",
            _I,
        ),
        "access-control-implementation",
    ),
    (
        re.compile(r"\b(?:audit[.\s_-]log[.\s_-]impl|audit[.\s_-]trail)\b", _I),
        "audit-log-implementation",
    ),
    (
        re.compile(
            r"\b(?:encrypt[.\s_-]impl|encrypt[.\s_-]at[.\s_-]rest|encrypt[.\s_-]in[.\s_-]transit)\b",
            _I,
        ),
        "encryption-implementation",
    ),
    (
        re.compile(r"\b(?:secret[.\s_-]scan|credential[.\s_-]leak)\b", _I),
        "secret-scanning",
    ),
    (
        re.compile(
            r"\b(?:vuln[.\s_-]patch|dep[.\s_-]audit|snyk\b|security[.\s_-]patch)\b", _I
        ),
        "vulnerability-patching",
    ),
    (
        re.compile(
            r"\b(?:gdpr[.\s_-]impl|data[.\s_-]deletion|right[.\s_-]to[.\s_-]erasure)\b",
            _I,
        ),
        "gdpr-compliance-implementation",
    ),
    # frontend-and-mobile
    (
        re.compile(r"\b(?:a11y[.\s_-]fix|wcag[.\s_-]fix|aria[.\s_-]fix)\b", _I),
        "accessibility-remediation",
    ),
    (
        re.compile(r"\b(?:i18n[.\s_-]impl|translat[.\s_-]add|locale[.\s_-]add)\b", _I),
        "i18n-implementation",
    ),
    (
        re.compile(
            r"\b(?:web[.\s_-]perf[.\s_-]optim|core[.\s_-]web[.\s_-]vital|code[.\s_-]split)\b",
            _I,
        ),
        "web-performance-optimisation",
    ),
    (
        re.compile(r"\b(?:chaos[.\s_-]experiment|fault[.\s_-]inject)\b", _I),
        "chaos-experiment",
    ),
    # architecture
    (
        re.compile(
            r"\b(?:event[.\s_-]sour|event[.\s_-]store[.\s_-]impl|append[.\s_-]only)\b",
            _I,
        ),
        "event-sourcing-implementation",
    ),
    (re.compile(r"\b(?:saga[.\s_-]impl|orchestrat[.\s_-]saga)\b", _I), "saga-pattern"),
    (
        re.compile(r"\b(?:outbox[.\s_-]impl|transactional[.\s_-]outbox)\b", _I),
        "outbox-pattern",
    ),
    (
        re.compile(
            r"\b(?:cqrs[.\s_-]impl|command[.\s_-]handler|query[.\s_-]handler)\b", _I
        ),
        "cqrs-implementation",
    ),
    # developer-experience
    (
        re.compile(
            r"\b(?:monorepo[.\s_-]config|nx[.\s_-]config|turborepo[.\s_-]config)\b", _I
        ),
        "monorepo-configuration",
    ),
    (
        re.compile(
            r"\b(?:performance[.\s_-]profil|cpu[.\s_-]profil|flame[.\s_-]graph)\b", _I
        ),
        "performance-profiling",
    ),
    (
        re.compile(
            r"\b(?:memory[.\s_-]leak|heap[.\s_-]dump|oom\b|out[.\s_-]of[.\s_-]memory)\b",
            _I,
        ),
        "memory-leak-fix",
    ),
    (
        re.compile(
            r"\b(?:latency[.\s_-]reduc|p99[.\s_-]reduc|response[.\s_-]time[.\s_-]improv)\b",
            _I,
        ),
        "latency-reduction",
    ),
    (
        re.compile(
            r"\b(?:cli[.\s_-]tool|command[.\s_-]line|argparse|click\b|cobra\b)\b", _I
        ),
        "cli-tool-development",
    ),
    (
        re.compile(
            r"\b(?:dependency[.\s_-]upgrade|dependency[.\s_-]updat|renovate|dependabot)\b",
            _I,
        ),
        "dependency-upgrade",
    ),
]

# Tool patterns: list[tuple[re.Pattern, str]]
TOOL_PATTERNS: list[tuple[re.Pattern, str]] = [
    # databases
    (re.compile(r"\b(?:postgresql|postgres)\b|psycopg", _I), "PostgreSQL"),
    (re.compile(r"\bmysql\b", _I), "MySQL"),
    (re.compile(r"\bsqlite\b", _I), "SQLite"),
    (re.compile(r"\b(?:mongodb|pymongo)\b|mongoose\b", _I), "MongoDB"),
    (re.compile(r"\bdynamodb\b", _I), "DynamoDB"),
    (re.compile(r"\bcassandra\b", _I), "Cassandra"),
    (re.compile(r"\bredis\b", _I), "Redis"),
    (re.compile(r"\b(?:elasticsearch|opensearch)\b", _I), "Elasticsearch"),
    (re.compile(r"\bneo4j\b", _I), "Neo4j"),
    (re.compile(r"\bkuzu\b", _I), "Kuzu"),
    (re.compile(r"\bsnowflake\b", _I), "Snowflake"),
    (re.compile(r"\bbigquery\b", _I), "BigQuery"),
    (re.compile(r"\bredshift\b", _I), "Redshift"),
    (re.compile(r"\bclickhouse\b", _I), "ClickHouse"),
    (re.compile(r"\bdatabricks\b", _I), "Databricks"),
    (re.compile(r"\bpinecone\b", _I), "Pinecone"),
    (re.compile(r"\bweaviate\b", _I), "Weaviate"),
    (re.compile(r"\bqdrant\b", _I), "Qdrant"),
    (re.compile(r"\bmilvus\b", _I), "Milvus"),
    (re.compile(r"\bchroma\b|chromadb", _I), "Chroma"),
    (re.compile(r"\btimescaledb\b", _I), "TimescaleDB"),
    (re.compile(r"\binfluxdb\b", _I), "InfluxDB"),
    # messaging
    (re.compile(r"\bkafka\b", _I), "Apache Kafka"),
    (re.compile(r"\brabbitmq\b", _I), "RabbitMQ"),
    (re.compile(r"\bnats\b", _I), "NATS"),
    (re.compile(r"\bkinesis\b", _I), "Kinesis"),
    (re.compile(r"\bpulsar\b", _I), "Apache Pulsar"),
    (re.compile(r"\bsqs\b|simple[.\s_-]queue", _I), "AWS SQS"),
    # observability
    (re.compile(r"\bdatadog\b", _I), "Datadog"),
    (re.compile(r"\bgrafana\b", _I), "Grafana"),
    (re.compile(r"\bprometheus\b", _I), "Prometheus"),
    (re.compile(r"\bsentry\b", _I), "Sentry"),
    (re.compile(r"\b(?:opentelemetry|otel)\b", _I), "OpenTelemetry"),
    (re.compile(r"\bpagerduty\b", _I), "PagerDuty"),
    (re.compile(r"\bnew[.\s_-]relic\b", _I), "New Relic"),
    (re.compile(r"\bhoneycomb\b", _I), "Honeycomb"),
    # infra-tools
    (re.compile(r"\bterraform\b", _I), "Terraform"),
    (re.compile(r"\bpulumi\b", _I), "Pulumi"),
    (re.compile(r"\b(?:kubernetes|k8s)\b", _I), "Kubernetes"),
    (re.compile(r"\bhelm\b", _I), "Helm"),
    (re.compile(r"\bdocker\b", _I), "Docker"),
    (re.compile(r"\bvault\b", _I), "Vault"),
    (re.compile(r"\bargo[.\s_-]?cd\b|argocd\b", _I), "ArgoCD"),
    # ci-cd
    (re.compile(r"\bgithub[.\s_-]action|\.github/workflows", _I), "GitHub Actions"),
    (re.compile(r"\bgitlab[.\s_-]?ci|\.gitlab-ci", _I), "GitLab CI"),
    (re.compile(r"\bcircle[.\s_-]?ci\b", _I), "CircleCI"),
    (re.compile(r"\bjenkins\b", _I), "Jenkins"),
    (re.compile(r"\bbuildkite\b", _I), "Buildkite"),
    (re.compile(r"\bfastlane\b", _I), "Fastlane"),
    # data-tools
    (re.compile(r"\bairflow\b", _I), "Airflow"),
    (re.compile(r"\bprefect\b", _I), "Prefect"),
    (re.compile(r"\bdagster\b", _I), "Dagster"),
    (re.compile(r"\bdbt\b", _I), "dbt"),
    (re.compile(r"\bdebezium\b", _I), "Debezium"),
    (re.compile(r"\bairbyte\b", _I), "Airbyte"),
    # ml-tools
    (re.compile(r"\bmlflow\b", _I), "MLflow"),
    (
        re.compile(r"\b(?:weights[.\s_-]?&[.\s_-]?biases|wandb)\b", _I),
        "Weights & Biases",
    ),
    (re.compile(r"\blangchain\b", _I), "LangChain"),
    (re.compile(r"\b(?:llamaindex|llama[.\s_-]index)\b", _I), "LlamaIndex"),
    (re.compile(r"\b(?:hugging[.\s_-]face|transformers)\b", _I), "Hugging Face"),
    (re.compile(r"\bsagemaker\b", _I), "SageMaker"),
    # testing-tools
    (re.compile(r"\bplaywright\b", _I), "Playwright"),
    (re.compile(r"\bcypress\b", _I), "Cypress"),
    (re.compile(r"\bselenium\b", _I), "Selenium"),
    (re.compile(r"\btestcontainer\b", _I), "TestContainers"),
    (re.compile(r"\bk6\b", _I), "k6"),
    (re.compile(r"\blocust\b", _I), "Locust"),
    (re.compile(r"\bsonarqube\b", _I), "SonarQube"),
    (re.compile(r"\bsnyk\b", _I), "Snyk"),
    # communication
    (re.compile(r"\btwilio\b", _I), "Twilio"),
    (re.compile(r"\bsendgrid\b", _I), "SendGrid"),
    (re.compile(r"\baws[.\s_-]ses\b", _I), "Amazon SES"),
    # payments
    (re.compile(r"\bstripe\b", _I), "Stripe"),
    (re.compile(r"\bpaypal\b", _I), "PayPal"),
    (re.compile(r"\badyen\b", _I), "Adyen"),
    (re.compile(r"\bbraintree\b", _I), "Braintree"),
    # auth-providers
    (re.compile(r"\bauth0\b", _I), "Auth0"),
    (re.compile(r"\bokta\b", _I), "Okta"),
    (re.compile(r"\bkeycloak\b", _I), "Keycloak"),
    (re.compile(r"\bcognito\b", _I), "Cognito"),
    (re.compile(r"\bclerk\b", _I), "Clerk"),
    # feature-flags
    (re.compile(r"\blaunchdarkly\b", _I), "LaunchDarkly"),
    (re.compile(r"\bunleash\b", _I), "Unleash"),
    (re.compile(r"\bgrowthbook\b", _I), "GrowthBook"),
    (re.compile(r"\bstatsig\b", _I), "Statsig"),
    # build / frontend
    (re.compile(r"\bvite\b", _I), "Vite"),
    (re.compile(r"\bwebpack\b", _I), "Webpack"),
    (re.compile(r"\b(?:next\.js|nextjs)\b", _I), "Next.js"),
    (re.compile(r"\bstorybook\b", _I), "Storybook"),
]

# Framework patterns: list[tuple[re.Pattern, str]]
FRAMEWORK_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Python
    (re.compile(r"\bfastapi\b", _I), "FastAPI"),
    (re.compile(r"\bdjango\b", _I), "Django"),
    (re.compile(r"\bflask\b", _I), "Flask"),
    (re.compile(r"\bstarlette\b", _I), "Starlette"),
    (re.compile(r"\bsqlalchemy\b", _I), "SQLAlchemy"),
    (re.compile(r"\bcelery\b", _I), "Celery"),
    (re.compile(r"\bpydantic\b", _I), "Pydantic"),
    (re.compile(r"\balembic\b", _I), "Alembic"),
    (re.compile(r"\bpytest\b", _I), "pytest"),
    (re.compile(r"\bpandas\b", _I), "Pandas"),
    (re.compile(r"\bnumpy\b", _I), "NumPy"),
    (re.compile(r"\bpytorch\b", _I), "PyTorch"),
    (re.compile(r"\btensorflow\b", _I), "TensorFlow"),
    (re.compile(r"\b(?:scikit[.\s_-]learn|sklearn)\b", _I), "Scikit-learn"),
    # TypeScript / JavaScript
    (re.compile(r"\breact\b", _I), "React"),
    (re.compile(r"\b(?:next\.js|nextjs)\b", _I), "Next.js"),
    (re.compile(r"\b(?:nestjs|nest\.js)\b", _I), "NestJS"),
    (re.compile(r"\bexpress\b", _I), "Express"),
    (re.compile(r"\bfastify\b", _I), "Fastify"),
    (re.compile(r"\btrpc\b", _I), "tRPC"),
    (re.compile(r"\bvue\b", _I), "Vue"),
    (re.compile(r"\bangular\b", _I), "Angular"),
    (re.compile(r"\bsvelte\b", _I), "Svelte"),
    (re.compile(r"\bprisma\b", _I), "Prisma"),
    (re.compile(r"\bdrizzle\b", _I), "Drizzle"),
    (re.compile(r"\bjest\b", _I), "Jest"),
    (re.compile(r"\bvitest\b", _I), "Vitest"),
    (re.compile(r"\bzustand\b", _I), "Zustand"),
    (re.compile(r"\bredux\b", _I), "Redux"),
    # Go
    (re.compile(r"\bgin\b", _I), "Gin"),
    (re.compile(r"\becho\b", _I), "Echo"),
    (re.compile(r"\bfiber\b", _I), "Fiber"),
    # Java
    (re.compile(r"\bspring[.\s_-]boot\b", _I), "Spring Boot"),
    (re.compile(r"\bquarkus\b", _I), "Quarkus"),
    (re.compile(r"\bktor\b", _I), "Ktor"),
    (re.compile(r"\bjunit\b", _I), "JUnit"),
    (re.compile(r"\bmockito\b", _I), "Mockito"),
    # Swift / iOS
    (re.compile(r"\bswiftui\b", _I), "SwiftUI"),
    (re.compile(r"\buikit\b", _I), "UIKit"),
    # Dart / Flutter
    (re.compile(r"\bflutter\b", _I), "Flutter"),
    # Ruby
    (re.compile(r"\brails\b|ruby[.\s_-]on[.\s_-]rails", _I), "Rails"),
    (re.compile(r"\brspec\b", _I), "RSpec"),
    # Rust
    (re.compile(r"\baxum\b", _I), "Axum"),
    (re.compile(r"\bactix\b", _I), "Actix Web"),
    (re.compile(r"\btokio\b", _I), "Tokio"),
    # C#
    (re.compile(r"\b(?:asp\.net|aspnetcore)\b", _I), "ASP.NET Core"),
    (re.compile(r"\bblazor\b", _I), "Blazor"),
    # PHP
    (re.compile(r"\blaravel\b", _I), "Laravel"),
    (re.compile(r"\bsymfony\b", _I), "Symfony"),
    # Elixir
    (re.compile(r"\bphoenix\b", _I), "Phoenix"),
    # Scala
    (re.compile(r"\bakka\b", _I), "Akka"),
    (re.compile(r"\bzio\b", _I), "ZIO"),
]
