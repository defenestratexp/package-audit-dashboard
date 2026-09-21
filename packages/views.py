"""Views for package audit dashboard."""
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from .storage import storage_client


def health(request):
    """Health check endpoint for Kubernetes probes."""
    return HttpResponse("OK", content_type="text/plain")


def dashboard(request):
    """Main dashboard showing all hosts."""
    hosts = storage_client.get_latest_hosts()
    dates = storage_client.get_available_dates()
    
    # Get package count for each host
    for host in hosts:
        report = storage_client.get_host_report(host["hostname"])
        if report:
            host["package_count"] = report.get("package_count", 0)
            host["os_distribution"] = report.get("os_distribution", "Unknown")
            host["os_version"] = report.get("os_version", "")
            host["scan_time"] = report.get("scan_time", "")
    
    return render(request, "packages/dashboard.html", {
        "hosts": hosts,
        "dates": dates,
        "host_count": len(hosts),
    })


def host_detail(request, hostname):
    """Show all packages on a specific host."""
    date = request.GET.get("date")
    report = storage_client.get_host_report(hostname, date)
    dates = storage_client.get_available_dates()
    
    if not report:
        return render(request, "packages/error.html", {
            "message": f"No report found for host: {hostname}"
        })
    
    # Sort packages by name
    packages = sorted(report.get("packages", []), key=lambda x: x["name"])
    
    return render(request, "packages/host_detail.html", {
        "hostname": hostname,
        "report": report,
        "packages": packages,
        "dates": dates,
        "selected_date": date,
    })


def search(request):
    """Search for a package across all hosts."""
    query = request.GET.get("q", "")
    results = []
    
    if query and len(query) >= 2:
        results = storage_client.search_package(query)
    
    hosts = storage_client.get_latest_hosts()
    
    return render(request, "packages/search.html", {
        "query": query,
        "results": results,
        "result_count": len(results),
        "hosts": hosts,
    })


def compare(request):
    """Compare packages between two hosts."""
    host1 = request.GET.get("host1", "")
    host2 = request.GET.get("host2", "")
    
    hosts = storage_client.get_latest_hosts()
    comparison = None
    
    if host1 and host2:
        comparison = storage_client.compare_hosts(host1, host2)
    
    return render(request, "packages/compare.html", {
        "hosts": hosts,
        "host1": host1,
        "host2": host2,
        "comparison": comparison,
    })


# Security-critical packages to track
SECURITY_PACKAGES = [
    "openssl",
    "openssh-client",
    "openssh-server",
    "sudo",
    "curl",
    "wget",
    "gnupg",
    "ca-certificates",
    "libssl3",
    "libssl1.1",
    "libcrypto3",
    "linux-image-generic",
    "linux-headers-generic",
    "apt",
    "dpkg",
    "systemd",
    "polkit",
    "pam",
    "libpam-modules",
    "shadow",
    "passwd",
    "login",
    "coreutils",
    "bash",
    "tar",
    "gzip",
    "iptables",
    "nftables",
    "ufw",
    "apparmor",
]


def security_packages(request):
    """Show security-critical packages across all hosts."""
    hosts = storage_client.get_latest_hosts()

    # Build version matrix: {package_name: {hostname: version}}
    package_matrix = {pkg: {} for pkg in SECURITY_PACKAGES}
    host_names = []

    for host in hosts:
        hostname = host["hostname"]
        host_names.append(hostname)
        report = storage_client.get_host_report(hostname)

        if report:
            packages = {p["name"]: p["version"] for p in report.get("packages", [])}
            for sec_pkg in SECURITY_PACKAGES:
                if sec_pkg in packages:
                    package_matrix[sec_pkg][hostname] = packages[sec_pkg]

    # Convert to list format for template and detect inconsistencies
    security_data = []
    for pkg_name in SECURITY_PACKAGES:
        versions = package_matrix[pkg_name]
        unique_versions = set(versions.values())

        # Package is inconsistent if there are multiple different versions
        has_inconsistency = len(unique_versions) > 1
        # Package is missing from some hosts
        missing_count = len(host_names) - len(versions)

        security_data.append({
            "name": pkg_name,
            "versions": versions,
            "unique_versions": list(unique_versions),
            "has_inconsistency": has_inconsistency,
            "missing_count": missing_count,
            "installed_count": len(versions),
        })

    # Sort: packages with inconsistencies first, then by name
    security_data.sort(key=lambda x: (not x["has_inconsistency"], x["name"]))

    # Calculate summary stats
    total_inconsistencies = sum(1 for p in security_data if p["has_inconsistency"])
    total_missing = sum(1 for p in security_data if p["missing_count"] > 0)

    return render(request, "packages/security_packages.html", {
        "security_data": security_data,
        "host_names": sorted(host_names),
        "host_count": len(host_names),
        "total_packages": len(SECURITY_PACKAGES),
        "total_inconsistencies": total_inconsistencies,
        "total_missing": total_missing,
    })


def api_hosts(request):
    """API endpoint for hosts list."""
    hosts = storage_client.get_latest_hosts()
    return JsonResponse({"hosts": hosts})


def api_host_packages(request, hostname):
    """API endpoint for host packages."""
    report = storage_client.get_host_report(hostname)
    if report:
        return JsonResponse(report)
    return JsonResponse({"error": "Host not found"}, status=404)
