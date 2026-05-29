"""
Cohesity Smart Files routes — OpenWebUI Knowledge integration.

Exposes three endpoints used by the Cohesity Gaia Knowledge Filter:

  GET  /api/v1/cohesity/views
       List all Smart Files views on the Cohesity cluster.
       Returns: {"views": [{"name", "description", "id", "protocol_access"}]}

  POST /api/v1/cohesity/views/{view_name}/search
       Full-text search within a view.  Returns file metadata plus
       extracted text content for recognised text/document types.
       Body:    {"query": "...", "limit": 10}
       Returns: {"view", "query", "results": [{"filename", "path", "size_bytes",
                 "modified", "type", "content", "content_truncated"}]}

  GET  /api/v1/cohesity/views/{view_name}/browse
       Browse the top-level directory of a view (directory listing).
       Returns: {"view", "entries": [{"name", "path", "type", "size_bytes", "modified"}]}

Environment variables (set in .env / docker-compose):
  COHESITY_CLUSTER_URL   e.g. https://cohesity.corp.example.com
  COHESITY_API_KEY       preferred auth method (API key)
  COHESITY_USERNAME      fallback: username for session-token auth
  COHESITY_PASSWORD      fallback: password
  COHESITY_DOMAIN        auth domain, default LOCAL
  COHESITY_VERIFY_SSL    default false (self-signed certs are common)
  COHESITY_MAX_FILE_KB   max text file size to download, default 256 KB
"""

from __future__ import annotations

import io
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.api.dependencies import require_session
from backend.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cohesity", tags=["Cohesity Smart Files"])

# ── Text-extractable extensions ──────────────────────────────────────────────
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".log",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".sql",
    ".html", ".htm", ".xml", ".css",
    ".r", ".scala", ".kt", ".swift", ".c", ".cpp", ".h",
}
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx", ".doc"}


# ── Cohesity API client ───────────────────────────────────────────────────────

class CohesityClient:
    """
    Thin async wrapper around the Cohesity DataCloud REST API.

    Authentication precedence:
      1. API key  →  apiKey: <key>  header  (preferred)
      2. Username / password  →  POST /v2/users/sessions  → Bearer token
    """

    def __init__(self) -> None:
        s = get_settings()
        self.cluster_url = s.cohesity_cluster_url.rstrip("/")
        self.api_key = s.cohesity_api_key
        self.username = s.cohesity_username
        self.password = s.cohesity_password
        self.domain = s.cohesity_domain or "LOCAL"
        self.verify_ssl = s.cohesity_verify_ssl
        self.max_bytes = s.cohesity_max_file_kb * 1024

        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # ── Auth ──────────────────────────────────────────────────────────────

    async def _get_auth_headers(self) -> dict:
        if self.api_key:
            return {
                "apiKey": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        token = await self._get_session_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get_session_token(self) -> str:
        """Obtain (or refresh) a session token via username/password."""
        if self._token and time.time() < self._token_expiry - 30:
            return self._token

        if not self.username or not self.password:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Cohesity credentials not configured. "
                    "Set COHESITY_API_KEY or COHESITY_USERNAME + COHESITY_PASSWORD."
                ),
            )

        url = f"{self.cluster_url}/v2/users/sessions"
        payload = {"domain": self.domain, "username": self.username, "password": self.password}
        logger.info("cohesity: obtaining session token from %s", url)
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=15) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("accessToken") or data.get("token") or ""
                expire_ts = data.get("tokenExpireTime") or data.get("expiresAt") or 0
                self._token_expiry = float(expire_ts) if expire_ts else time.time() + 3600
                if not self._token:
                    raise HTTPException(status_code=502, detail=f"Cohesity auth: no token in response — {resp.text[:200]}")
                logger.info("cohesity: session token obtained (expires ~%ds)", self._token_expiry - time.time())
                return self._token
            logger.error("cohesity auth HTTP %d: %s", resp.status_code, resp.text[:300])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Cohesity authentication failed: HTTP {resp.status_code} — {resp.text[:200]}",
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("cohesity auth error: %s", exc)
            raise HTTPException(status_code=502, detail=f"Cohesity connection error: {exc}")

    # ── Demo mode (no cluster configured) ─────────────────────────────────

    def _is_demo_mode(self) -> bool:
        return not self.cluster_url

    _DEMO_VIEWS = [
        {"id": 1001, "name": "FinancialReports", "description": "Quarterly financial reports and audits", "protocols": ["SMB", "NFS"], "storage_domain": "DefaultStorageDomain"},
        {"id": 1002, "name": "LegalDocuments",   "description": "Contracts, NDAs, and compliance docs",  "protocols": ["SMB"],        "storage_domain": "DefaultStorageDomain"},
        {"id": 1003, "name": "EngineeringDocs",  "description": "Architecture docs, runbooks, RFCs",     "protocols": ["NFS"],        "storage_domain": "DefaultStorageDomain"},
        {"id": 1004, "name": "HRPolicies",       "description": "HR policies, handbooks, job descriptions", "protocols": ["SMB"],     "storage_domain": "DefaultStorageDomain"},
    ]

    _DEMO_FILES: dict[str, list[dict]] = {
        "FinancialReports": [
            {
                "filename": "Q4_2025_Earnings_Report.txt",
                "path": "/FinancialReports/Q4_2025_Earnings_Report.txt",
                "view": "FinancialReports", "size_bytes": 4200, "type": "file",
                "content": (
                    "ACME CORP — Q4 2025 EARNINGS REPORT\n"
                    "=====================================\n"
                    "Total Revenue:        $487.3M  (+18% YoY)\n"
                    "Gross Profit:         $312.1M  (64% margin)\n"
                    "Operating Income:     $127.4M  (+22% YoY)\n"
                    "Net Income:           $98.7M   (+31% YoY)\n"
                    "EPS (diluted):        $2.14\n\n"
                    "SEGMENT BREAKDOWN\n"
                    "-----------------\n"
                    "Cloud Services:   $201.5M  (+34% YoY) — strongest growth driver\n"
                    "On-Prem Software: $189.4M  (+8% YoY)  — steady; migration to cloud ongoing\n"
                    "Professional Svcs: $96.4M  (+11% YoY)\n\n"
                    "GUIDANCE — Q1 2026\n"
                    "------------------\n"
                    "Revenue:     $510M–$525M\n"
                    "Non-GAAP EPS: $2.20–$2.28\n\n"
                    "CEO COMMENTARY\n"
                    "--------------\n"
                    "We closed the year with record ARR of $1.73B. Cloud-first deals grew 41% "
                    "in the quarter, and net revenue retention reached 124%, both all-time highs. "
                    "Our DataProtect and DataInsights platforms drove cross-sell in 73% of new enterprise wins."
                ),
            },
            {
                "filename": "2025_Annual_Budget.csv",
                "path": "/FinancialReports/2025_Annual_Budget.csv",
                "view": "FinancialReports", "size_bytes": 1800, "type": "file",
                "content": (
                    "Department,Q1_Budget,Q2_Budget,Q3_Budget,Q4_Budget,Annual_Total\n"
                    "Engineering,12500000,13000000,13500000,14000000,53000000\n"
                    "Sales & Marketing,8000000,9500000,9000000,10500000,37000000\n"
                    "G&A,3200000,3200000,3200000,3200000,12800000\n"
                    "R&D,6000000,6500000,7000000,7500000,27000000\n"
                    "Customer Success,2800000,3000000,3100000,3100000,12000000\n"
                    "TOTAL,32500000,35200000,35800000,38300000,141800000\n"
                ),
            },
        ],
        "LegalDocuments": [
            {
                "filename": "MSA_Template_v3.txt",
                "path": "/LegalDocuments/MSA_Template_v3.txt",
                "view": "LegalDocuments", "size_bytes": 3100, "type": "file",
                "content": (
                    "MASTER SERVICES AGREEMENT — TEMPLATE v3.0\n"
                    "==========================================\n"
                    "This Master Services Agreement ('Agreement') is entered into between ACME Corp "
                    "('Company') and the customer entity executing an Order Form referencing this Agreement.\n\n"
                    "1. SERVICES\n"
                    "   Company will provide the software services described in the applicable Order Form.\n\n"
                    "2. PAYMENT TERMS\n"
                    "   Invoices are due net-30. Late payments accrue interest at 1.5% per month.\n\n"
                    "3. DATA SECURITY\n"
                    "   Company maintains SOC 2 Type II certification. Data is encrypted at rest (AES-256) "
                    "and in transit (TLS 1.3). Customer data is never used for model training.\n\n"
                    "4. LIABILITY\n"
                    "   Each party's liability is capped at fees paid in the 12 months preceding the claim.\n\n"
                    "5. TERM\n"
                    "   Agreement commences on the Order Form Effective Date and continues for 12 months, "
                    "auto-renewing annually unless either party gives 60-day written notice.\n"
                ),
            },
        ],
        "EngineeringDocs": [
            {
                "filename": "DataProtect_Architecture.md",
                "path": "/EngineeringDocs/DataProtect_Architecture.md",
                "view": "EngineeringDocs", "size_bytes": 5200, "type": "file",
                "content": (
                    "# DataProtect Platform — Architecture Overview\n\n"
                    "## Components\n\n"
                    "### Backup Engine\n"
                    "- Incremental-forever deduplication at the variable-length block level\n"
                    "- Compression ratio: average 3.5:1 for mixed workloads\n"
                    "- Supports: VMware, Hyper-V, NAS (NFS/SMB), Physical servers, Databases (Oracle, SQL, MongoDB)\n\n"
                    "### Storage Fabric\n"
                    "- Distributed key-value store (Magneto) for metadata\n"
                    "- Chunk store with content-addressed storage (CAS)\n"
                    "- Replication: sync or async, RPO < 30 seconds for sync\n\n"
                    "### Recovery\n"
                    "- Instant recovery via NFS/iSCSI mount (no copy needed)\n"
                    "- RTO: < 2 minutes for VM recovery; < 30 seconds for file-level\n"
                    "- Test & dev clones: space-efficient writable snapshots\n\n"
                    "## SLAs\n"
                    "- Ingestion throughput: 120 GB/h per node\n"
                    "- Recovery throughput: 80 GB/h per node\n"
                    "- Metadata query p99 latency: < 50 ms\n"
                ),
            },
            {
                "filename": "API_Runbook.md",
                "path": "/EngineeringDocs/API_Runbook.md",
                "view": "EngineeringDocs", "size_bytes": 2800, "type": "file",
                "content": (
                    "# API Gateway Runbook\n\n"
                    "## Endpoints\n"
                    "- Production: https://api.acme.corp/v2\n"
                    "- Staging:    https://api-staging.acme.corp/v2\n\n"
                    "## Auth\n"
                    "All endpoints require Bearer token. Token lifetime: 24h. Refresh via /auth/refresh.\n\n"
                    "## Rate Limits\n"
                    "- Standard tier: 1 000 req/min\n"
                    "- Enterprise tier: 10 000 req/min\n"
                    "- Burst allowance: 2x for up to 10 seconds\n\n"
                    "## On-Call Escalation\n"
                    "1. PagerDuty → API-Ops team (< 5 min SLA)\n"
                    "2. Slack: #api-oncall\n"
                    "3. Escalate to Platform Eng if not resolved in 20 min\n"
                ),
            },
        ],
        "HRPolicies": [
            {
                "filename": "PTO_Policy_2025.txt",
                "path": "/HRPolicies/PTO_Policy_2025.txt",
                "view": "HRPolicies", "size_bytes": 2100, "type": "file",
                "content": (
                    "ACME CORP — PAID TIME OFF POLICY 2025\n"
                    "======================================\n"
                    "Effective: January 1 2025\n\n"
                    "ACCRUAL\n"
                    "  Years 0–2:   15 days / year  (1.25 days / month)\n"
                    "  Years 3–5:   20 days / year  (1.67 days / month)\n"
                    "  Years 6+:    25 days / year  (2.08 days / month)\n\n"
                    "CARRYOVER\n"
                    "  Maximum carryover: 10 days into the new calendar year.\n"
                    "  Unused PTO above 10 days is forfeited on Jan 31.\n\n"
                    "SICK LEAVE\n"
                    "  Separate 10-day sick leave bank. Does not carry over.\n\n"
                    "HOLIDAYS\n"
                    "  12 company-wide holidays per year (list on HR Portal).\n"
                    "  Floating holiday: 1 per year (must be used by Dec 31).\n\n"
                    "REQUESTING TIME OFF\n"
                    "  Submit requests in Workday ≥ 2 weeks in advance for planned leave.\n"
                    "  For unplanned absence, notify your manager before 9 AM."
                ),
            },
            {
                "filename": "Remote_Work_Policy.txt",
                "path": "/HRPolicies/Remote_Work_Policy.txt",
                "view": "HRPolicies", "size_bytes": 1800, "type": "file",
                "content": (
                    "ACME CORP — REMOTE WORK POLICY 2025\n"
                    "====================================\n"
                    "ACME operates a hybrid-first model. Employees may work remotely up to 3 days per week.\n\n"
                    "ELIGIBILITY\n"
                    "  All full-time employees past their 90-day probation period are eligible.\n\n"
                    "CORE HOURS\n"
                    "  All employees must be reachable 10 AM–3 PM in their team's primary time zone.\n\n"
                    "HOME OFFICE STIPEND\n"
                    "  $750 one-time setup stipend upon approval.\n"
                    "  $50/month ongoing for internet reimbursement.\n\n"
                    "SECURITY REQUIREMENTS\n"
                    "  VPN required for accessing internal systems.\n"
                    "  Endpoint protection (CrowdStrike) must be installed and active.\n"
                    "  Public Wi-Fi prohibited without VPN.\n"
                ),
            },
        ],
    }

    def _demo_search(self, view_name: str, query: str, limit: int) -> list[dict]:
        """Return demo results for the given view, filtered by query keywords."""
        all_files = self._DEMO_FILES.get(view_name, [])
        if not all_files:
            return []
        q_lower = query.lower()
        keywords = [w for w in q_lower.split() if len(w) > 2]
        scored = []
        for f in all_files:
            haystack = (f.get("filename", "") + " " + f.get("content", "")).lower()
            score = sum(1 for kw in keywords if kw in haystack)
            scored.append((score, f))
        scored.sort(key=lambda x: -x[0])
        return [f for _, f in scored[:limit]]

    # ── Cluster health check ───────────────────────────────────────────────

    def _check_configured(self) -> None:
        if not self.cluster_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Cohesity cluster URL not configured. "
                    "Set COHESITY_CLUSTER_URL in your .env file."
                ),
            )

    # ── Views (Smart Files shares) ─────────────────────────────────────────

    async def list_views(self) -> list[dict]:
        """List all Smart Files views from the Cohesity cluster."""
        if self._is_demo_mode():
            logger.info("cohesity: DEMO MODE — returning %d demo views", len(self._DEMO_VIEWS))
            return list(self._DEMO_VIEWS)
        self._check_configured()
        headers = await self._get_auth_headers()
        url = f"{self.cluster_url}/v2/file-services/views"
        logger.info("cohesity: listing views from %s", url)
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=30) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                views = data.get("views", data) if isinstance(data, dict) else data
                logger.info("cohesity: found %d view(s)", len(views))
                return views
            logger.warning("cohesity list_views HTTP %d: %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("cohesity list_views error: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc))

    # ── File search ────────────────────────────────────────────────────────

    async def search_files(self, view_name: str, query: str, limit: int = 10) -> list[dict]:
        """
        Search for files matching *query* within *view_name*.

        Tries endpoints in order:
          1. GET /v1/searchfiles   (widely available)
          2. POST /v2/data-protect/search/indexed-objects  (newer clusters)

        Falls back to demo data when COHESITY_CLUSTER_URL is not configured.
        """
        if self._is_demo_mode():
            results = self._demo_search(view_name, query, limit)
            logger.info("cohesity: DEMO MODE — view=%r query=%r → %d result(s)", view_name, query, len(results))
            return results
        self._check_configured()
        headers = await self._get_auth_headers()

        # ── Strategy 1: v1 searchfiles ────────────────────────────────────
        raw_files = await self._search_v1(headers, view_name, query, limit)
        if raw_files is not None:
            return raw_files

        # ── Strategy 2: v2 indexed-objects search ─────────────────────────
        raw_files = await self._search_v2_indexed(headers, view_name, query, limit)
        if raw_files is not None:
            return raw_files

        logger.warning("cohesity: no search strategy succeeded for view=%r query=%r", view_name, query)
        return []

    async def _search_v1(self, headers: dict, view_name: str, query: str, limit: int) -> list[dict] | None:
        """Try the Cohesity v1 searchfiles endpoint."""
        url = f"{self.cluster_url}/v1/searchfiles"
        params = {
            "searchString": query,
            "viewBoxNames": view_name,
            "pageSize": limit,
        }
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=30) as client:
                resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                files = data.get("files", [])
                logger.info("cohesity v1 search: view=%r query=%r → %d file(s)", view_name, query, len(files))
                return self._normalise_v1_files(files, view_name)
            if resp.status_code == 404:
                logger.debug("cohesity v1 search: endpoint not found, trying v2")
                return None
            logger.warning("cohesity v1 search HTTP %d: %s", resp.status_code, resp.text[:200])
            return None
        except Exception as exc:
            logger.debug("cohesity v1 search error: %s", exc)
            return None

    def _normalise_v1_files(self, raw: list[dict], view_name: str) -> list[dict]:
        results = []
        for item in raw:
            doc = item.get("fileDocument") or item
            filename = doc.get("filename") or doc.get("name") or ""
            dir_path = doc.get("directoryPath") or doc.get("dirPath") or f"/{view_name}"
            full_path = f"{dir_path}/{filename}".replace("//", "/")
            fstat = doc.get("fstatInfo") or {}
            size_bytes = fstat.get("size") or doc.get("sizeBytes") or 0
            mtime = fstat.get("mtimeUsecs") or doc.get("modifiedTimeMsecs") or 0
            file_type = "directory" if doc.get("type") == 1 or fstat.get("type") == "kDirectory" else "file"
            results.append({
                "filename": filename,
                "path": full_path,
                "view": view_name,
                "size_bytes": size_bytes,
                "modified_usecs": mtime,
                "type": file_type,
            })
        return results

    async def _search_v2_indexed(self, headers: dict, view_name: str, query: str, limit: int) -> list[dict] | None:
        """Try the Cohesity v2 indexed-objects search endpoint."""
        url = f"{self.cluster_url}/v2/data-protect/search/indexed-objects"
        payload = {
            "searchString": query,
            "objectTypes": ["Files"],
            "fileParams": {"viewName": view_name},
            "count": limit,
        }
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=30) as client:
                resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                files = data.get("files", data.get("objects", []))
                logger.info("cohesity v2 indexed search: view=%r query=%r → %d file(s)", view_name, query, len(files))
                return self._normalise_v2_files(files, view_name)
            logger.warning("cohesity v2 indexed search HTTP %d: %s", resp.status_code, resp.text[:200])
            return None
        except Exception as exc:
            logger.debug("cohesity v2 indexed search error: %s", exc)
            return None

    def _normalise_v2_files(self, raw: list[dict], view_name: str) -> list[dict]:
        results = []
        for item in raw:
            filename = item.get("name") or item.get("filename") or ""
            path = item.get("path") or item.get("fullPath") or f"/{view_name}/{filename}"
            results.append({
                "filename": filename,
                "path": path,
                "view": view_name,
                "size_bytes": item.get("sizeBytes") or item.get("size") or 0,
                "modified_usecs": item.get("modifiedTimeMsecs") or 0,
                "type": "file",
            })
        return results

    # ── Browse directory ──────────────────────────────────────────────────

    async def browse_directory(self, view_name: str, dir_path: str = "/") -> list[dict]:
        """List entries in a directory within a view."""
        self._check_configured()
        headers = await self._get_auth_headers()
        dir_path = dir_path if dir_path.startswith("/") else f"/{dir_path}"
        full_path = f"/{view_name}{dir_path}".replace("//", "/")

        url = f"{self.cluster_url}/v1/vm/dir"
        params = {
            "dirPath": full_path,
            "viewName": view_name,
            "statFileEntries": "true",
        }
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=30) as client:
                resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                entries = data.get("dirEntries", data.get("entries", []))
                logger.info("cohesity browse: view=%r path=%r → %d entries", view_name, dir_path, len(entries))
                return self._normalise_dir_entries(entries, view_name)
            logger.warning("cohesity browse HTTP %d: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("cohesity browse error: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc))

    def _normalise_dir_entries(self, raw: list[dict], view_name: str) -> list[dict]:
        results = []
        for entry in raw:
            name = entry.get("name", "")
            full_path = entry.get("fullPath") or entry.get("path") or f"/{view_name}/{name}"
            fstat = entry.get("fstatInfo") or {}
            entry_type = fstat.get("type") or entry.get("type") or "kFile"
            results.append({
                "name": name,
                "path": full_path,
                "type": "directory" if entry_type in ("kDirectory", "directory", 1) else "file",
                "size_bytes": fstat.get("size") or entry.get("sizeBytes") or 0,
                "modified_usecs": fstat.get("mtimeUsecs") or entry.get("modifiedTimeMsecs") or 0,
            })
        return results

    # ── File content download + extraction ────────────────────────────────

    async def get_file_content(self, view_name: str, file_path: str) -> dict:
        """
        Download a file and extract its text content.

        Returns a dict with:
          content          str | None — extracted text (None for binary/unsupported)
          content_truncated bool
          error            str | None — extraction error message
        """
        self._check_configured()
        headers = await self._get_auth_headers()
        # Remove auth JSON content-type for file download
        download_headers = {k: v for k, v in headers.items() if k != "Content-Type"}

        url = f"{self.cluster_url}/v1/downloadfiles"
        params = {"filePath": file_path, "viewName": view_name}
        logger.info("cohesity download: view=%r path=%r", view_name, file_path)

        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=60) as client:
                resp = await client.get(url, headers=download_headers, params=params)
            if resp.status_code != 200:
                return {"content": None, "content_truncated": False,
                        "error": f"Download failed: HTTP {resp.status_code}"}

            raw = resp.content
            return self._extract_text(file_path, raw)

        except Exception as exc:
            logger.error("cohesity download error: view=%r path=%r: %s", view_name, file_path, exc)
            return {"content": None, "content_truncated": False, "error": str(exc)}

    def _extract_text(self, file_path: str, raw: bytes) -> dict:
        """Extract readable text from raw file bytes based on extension."""
        import os
        ext = os.path.splitext(file_path)[1].lower()

        # ── Plain text ────────────────────────────────────────────────────
        if ext in TEXT_EXTENSIONS:
            try:
                text = raw.decode("utf-8", errors="replace")
                truncated = len(raw) > self.max_bytes
                if truncated:
                    text = text[:self.max_bytes].rsplit("\n", 1)[0] + "\n[… truncated …]"
                return {"content": text, "content_truncated": truncated, "error": None}
            except Exception as exc:
                return {"content": None, "content_truncated": False, "error": f"Text decode error: {exc}"}

        # ── PDF ───────────────────────────────────────────────────────────
        if ext in PDF_EXTENSIONS:
            return self._extract_pdf(raw)

        # ── DOCX ──────────────────────────────────────────────────────────
        if ext in DOCX_EXTENSIONS:
            return self._extract_docx(raw)

        # ── Unsupported binary ────────────────────────────────────────────
        return {"content": None, "content_truncated": False,
                "error": f"Binary file type ({ext}) — content not extractable"}

    def _extract_pdf(self, raw: bytes) -> dict:
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
            text = "\n".join(text_parts)
            truncated = len(text.encode()) > self.max_bytes
            if truncated:
                text = text[: self.max_bytes].rsplit("\n", 1)[0] + "\n[… truncated …]"
            return {"content": text, "content_truncated": truncated, "error": None}
        except ImportError:
            pass

        # Fallback: try pymupdf
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=raw, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            truncated = len(text.encode()) > self.max_bytes
            if truncated:
                text = text[: self.max_bytes].rsplit("\n", 1)[0] + "\n[… truncated …]"
            return {"content": text, "content_truncated": truncated, "error": None}
        except ImportError:
            pass

        return {
            "content": None,
            "content_truncated": False,
            "error": "PDF text extraction requires pdfplumber or PyMuPDF (pip install pdfplumber)",
        }

    def _extract_docx(self, raw: bytes) -> dict:
        try:
            import docx
            doc = docx.Document(io.BytesIO(raw))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            truncated = len(text.encode()) > self.max_bytes
            if truncated:
                text = text[: self.max_bytes].rsplit("\n", 1)[0] + "\n[… truncated …]"
            return {"content": text, "content_truncated": truncated, "error": None}
        except ImportError:
            return {
                "content": None,
                "content_truncated": False,
                "error": "DOCX extraction requires python-docx (pip install python-docx)",
            }
        except Exception as exc:
            return {"content": None, "content_truncated": False, "error": f"DOCX parse error: {exc}"}


# ── Request models ────────────────────────────────────────────────────────────

class SmartFileSearchRequest(BaseModel):
    query: str
    limit: int = 10
    include_content: bool = True  # attempt to download + extract text from matching files


# ── Route helpers ─────────────────────────────────────────────────────────────

def _format_timestamp(usecs: int) -> str:
    """Convert Cohesity microsecond timestamp to ISO-8601 string."""
    if not usecs:
        return ""
    try:
        from datetime import datetime, timezone
        # Cohesity timestamps are in microseconds since epoch
        secs = usecs / 1_000_000
        return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat()
    except Exception:
        return str(usecs)


# ── API routes ────────────────────────────────────────────────────────────────

@router.get("/views")
async def list_views(_api_key: str = Depends(require_session)):
    """
    List all Cohesity Smart Files views.
    Each view becomes a  cohesity:<ViewName>  collection in OpenWebUI.
    """
    client = CohesityClient()
    views = await client.list_views()

    normalised = []
    for v in views:
        name = v.get("name") or v.get("viewName") or ""
        if not name:
            continue
        protocols = [
            p.get("type") or p.get("protocol", "") if isinstance(p, dict) else str(p)
            for p in (v.get("protocolAccess") or v.get("protocols") or [])
        ]
        normalised.append({
            "id": v.get("viewId") or v.get("id") or "",
            "name": name,
            "description": v.get("description") or "",
            "protocols": protocols,
            "storage_domain": v.get("storageDomainName") or v.get("viewBoxName") or "",
        })

    logger.info("cohesity list_views → %d views", len(normalised))
    return {"views": normalised, "count": len(normalised)}


@router.post("/views/{view_name}/search")
async def search_view(
    view_name: str,
    body: SmartFileSearchRequest,
    _api_key: str = Depends(require_session),
):
    """
    Search files within a Cohesity Smart Files view.

    For text-based file types (.txt, .md, .csv, .py, .json, etc.) the backend
    downloads the file and injects its content into the response.  For PDFs
    and DOCX files it attempts text extraction.  Binary files return metadata only.

    This is the endpoint called by the Cohesity Gaia Knowledge Filter in OpenWebUI.
    """
    client = CohesityClient()
    raw_files = await client.search_files(view_name, body.query, body.limit)

    results = []
    for f in raw_files:
        if f.get("type") == "directory":
            continue  # skip directories in search results

        entry: dict = {
            "filename": f["filename"],
            "path": f["path"],
            "view": view_name,
            "size_bytes": f.get("size_bytes", 0),
            "modified": _format_timestamp(f.get("modified_usecs", 0)),
            "type": "file",
            "content": None,
            "content_truncated": False,
            "content_error": None,
        }

        if body.include_content and f.get("filename"):
            import os
            ext = os.path.splitext(f["filename"])[1].lower()
            # Only attempt download for extractable types
            if ext in (TEXT_EXTENSIONS | PDF_EXTENSIONS | DOCX_EXTENSIONS):
                content_result = await client.get_file_content(view_name, f["path"])
                entry["content"] = content_result.get("content")
                entry["content_truncated"] = content_result.get("content_truncated", False)
                entry["content_error"] = content_result.get("error")
            else:
                entry["content_error"] = f"Unsupported type ({ext}) — metadata only"

        results.append(entry)

    logger.info("cohesity search: view=%r query=%r → %d result(s), %d with content",
                view_name, body.query, len(results),
                sum(1 for r in results if r.get("content")))
    return {
        "view": view_name,
        "query": body.query,
        "results": results,
        "count": len(results),
    }


@router.get("/views/{view_name}/browse")
async def browse_view(
    view_name: str,
    path: str = "/",
    _api_key: str = Depends(require_session),
):
    """
    Browse the directory tree of a Cohesity Smart Files view.
    Useful for verifying the view is accessible and seeing what's in it.
    """
    client = CohesityClient()
    entries = await client.browse_directory(view_name, path)

    normalised = [
        {
            "name": e["name"],
            "path": e["path"],
            "type": e["type"],
            "size_bytes": e.get("size_bytes", 0),
            "modified": _format_timestamp(e.get("modified_usecs", 0)),
        }
        for e in entries
    ]
    return {"view": view_name, "path": path, "entries": normalised, "count": len(normalised)}
