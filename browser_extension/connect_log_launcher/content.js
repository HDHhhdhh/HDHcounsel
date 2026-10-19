(() => {
  const LINK_ID = "connectLogDesktopLink";
  const ADMIN_PATH = "/admin";

  function ensureConnectLogLink() {
    if (window.location.pathname !== ADMIN_PATH) return;
    if (document.getElementById(LINK_ID)) return;

    const linkArea = document.querySelector(".global-links");
    if (!linkArea) return;

    const link = document.createElement("a");
    link.id = LINK_ID;
    link.href = "connectlog://open";
    link.className = "btn secondary link-connect-log";
    link.textContent = "Connect Log";
    link.title = "5A Connect Log 앱 실행";
    link.setAttribute("aria-label", "5A Connect Log 앱 실행");
    linkArea.appendChild(link);
  }

  ensureConnectLogLink();

  const observer = new MutationObserver(ensureConnectLogLink);
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
