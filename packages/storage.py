"""Storage client for fetching package audit reports.

Supports both local filesystem and S3 backends based on STORAGE_TYPE env var.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from django.conf import settings


class LocalStorageClient:
    """Read package reports from local filesystem (NFS mount)."""

    def __init__(self):
        self.data_path = Path(getattr(settings, "LOCAL_DATA_PATH", "/data"))

    def get_latest_hosts(self) -> list[dict]:
        """Get list of all hosts from the latest folder."""
        latest_dir = self.data_path / "latest"
        hosts = []
        if not latest_dir.exists():
            return []

        for json_file in latest_dir.glob("*.json"):
            hostname = json_file.stem
            stat = json_file.stat()
            hosts.append({
                "hostname": hostname,
                "last_modified": datetime.fromtimestamp(stat.st_mtime),
                "size": stat.st_size,
            })
        return sorted(hosts, key=lambda x: x["hostname"])

    def get_host_report(self, hostname: str, date: Optional[str] = None) -> Optional[dict]:
        """Get package report for a specific host."""
        if date:
            report_path = self.data_path / "reports" / date / f"{hostname}.json"
        else:
            report_path = self.data_path / "latest" / f"{hostname}.json"

        if not report_path.exists():
            return None

        try:
            with open(report_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading report for {hostname}: {e}")
            return None

    def get_available_dates(self) -> list[str]:
        """Get list of available report dates."""
        reports_dir = self.data_path / "reports"
        if not reports_dir.exists():
            return []

        dates = [d.name for d in reports_dir.iterdir() if d.is_dir()]
        return sorted(dates, reverse=True)

    def search_package(self, package_name: str) -> list[dict]:
        """Search for a package across all hosts."""
        results = []
        hosts = self.get_latest_hosts()
        for host in hosts:
            report = self.get_host_report(host["hostname"])
            if report:
                for pkg in report.get("packages", []):
                    if package_name.lower() in pkg["name"].lower():
                        results.append({
                            "hostname": host["hostname"],
                            "name": pkg["name"],
                            "version": pkg["version"],
                            "source": pkg.get("source", "unknown"),
                        })
        return results

    def compare_hosts(self, host1: str, host2: str) -> dict:
        """Compare packages between two hosts."""
        report1 = self.get_host_report(host1)
        report2 = self.get_host_report(host2)
        if not report1 or not report2:
            return {"error": "Could not fetch reports for one or both hosts"}

        pkgs1 = {p["name"]: p for p in report1.get("packages", [])}
        pkgs2 = {p["name"]: p for p in report2.get("packages", [])}

        only_in_host1 = []
        only_in_host2 = []
        version_diff = []
        common = []

        for name, pkg in pkgs1.items():
            if name not in pkgs2:
                only_in_host1.append(pkg)
            elif pkgs2[name]["version"] != pkg["version"]:
                version_diff.append({
                    "name": name,
                    "version1": pkg["version"],
                    "version2": pkgs2[name]["version"],
                })
            else:
                common.append(pkg)

        for name, pkg in pkgs2.items():
            if name not in pkgs1:
                only_in_host2.append(pkg)

        return {
            "host1": host1,
            "host2": host2,
            "only_in_host1": sorted(only_in_host1, key=lambda x: x["name"]),
            "only_in_host2": sorted(only_in_host2, key=lambda x: x["name"]),
            "version_diff": sorted(version_diff, key=lambda x: x["name"]),
            "common_count": len(common),
        }


class S3StorageClient:
    """Read package reports from AWS S3."""

    def __init__(self):
        import boto3
        from botocore.exceptions import ClientError
        self.ClientError = ClientError
        self.s3 = boto3.client("s3", region_name=settings.S3_REGION)
        self.bucket = settings.S3_BUCKET

    def get_latest_hosts(self) -> list[dict]:
        """Get list of all hosts from the latest folder."""
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix="latest/",
            )
            hosts = []
            for obj in response.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".json"):
                    hostname = key.replace("latest/", "").replace(".json", "")
                    hosts.append({
                        "hostname": hostname,
                        "last_modified": obj["LastModified"],
                        "size": obj["Size"],
                    })
            return sorted(hosts, key=lambda x: x["hostname"])
        except self.ClientError as e:
            print(f"Error listing hosts: {e}")
            return []

    def get_host_report(self, hostname: str, date: Optional[str] = None) -> Optional[dict]:
        """Get package report for a specific host."""
        if date:
            key = f"reports/{date}/{hostname}.json"
        else:
            key = f"latest/{hostname}.json"
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(response["Body"].read().decode("utf-8"))
        except self.ClientError as e:
            print(f"Error getting report for {hostname}: {e}")
            return None

    def get_available_dates(self) -> list[str]:
        """Get list of available report dates."""
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix="reports/",
                Delimiter="/",
            )
            dates = []
            for prefix in response.get("CommonPrefixes", []):
                date = prefix["Prefix"].replace("reports/", "").rstrip("/")
                dates.append(date)
            return sorted(dates, reverse=True)
        except self.ClientError as e:
            print(f"Error listing dates: {e}")
            return []

    def search_package(self, package_name: str) -> list[dict]:
        """Search for a package across all hosts."""
        results = []
        hosts = self.get_latest_hosts()
        for host in hosts:
            report = self.get_host_report(host["hostname"])
            if report:
                for pkg in report.get("packages", []):
                    if package_name.lower() in pkg["name"].lower():
                        results.append({
                            "hostname": host["hostname"],
                            "name": pkg["name"],
                            "version": pkg["version"],
                            "source": pkg.get("source", "unknown"),
                        })
        return results

    def compare_hosts(self, host1: str, host2: str) -> dict:
        """Compare packages between two hosts."""
        report1 = self.get_host_report(host1)
        report2 = self.get_host_report(host2)
        if not report1 or not report2:
            return {"error": "Could not fetch reports for one or both hosts"}

        pkgs1 = {p["name"]: p for p in report1.get("packages", [])}
        pkgs2 = {p["name"]: p for p in report2.get("packages", [])}

        only_in_host1 = []
        only_in_host2 = []
        version_diff = []
        common = []

        for name, pkg in pkgs1.items():
            if name not in pkgs2:
                only_in_host1.append(pkg)
            elif pkgs2[name]["version"] != pkg["version"]:
                version_diff.append({
                    "name": name,
                    "version1": pkg["version"],
                    "version2": pkgs2[name]["version"],
                })
            else:
                common.append(pkg)

        for name, pkg in pkgs2.items():
            if name not in pkgs1:
                only_in_host2.append(pkg)

        return {
            "host1": host1,
            "host2": host2,
            "only_in_host1": sorted(only_in_host1, key=lambda x: x["name"]),
            "only_in_host2": sorted(only_in_host2, key=lambda x: x["name"]),
            "version_diff": sorted(version_diff, key=lambda x: x["name"]),
            "common_count": len(common),
        }


def get_storage_client():
    """Factory function to get the appropriate storage client."""
    storage_type = getattr(settings, "STORAGE_TYPE", "s3")
    if storage_type == "local":
        return LocalStorageClient()
    return S3StorageClient()


# Singleton instance
storage_client = get_storage_client()
