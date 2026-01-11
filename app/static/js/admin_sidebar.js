(() => {
  const body = document.body;
  const sidebar = document.getElementById("swmSidebar");
  const overlay = document.getElementById("swmSidebarOverlay");

  if (!sidebar) return;

  const KEY = "swm.sidebar.collapsed";

  const isMobile = () => window.matchMedia("(max-width: 991.98px)").matches;

  function applyInitialState() {
    // Mobile: começa fechado (offcanvas)
    if (isMobile()) {
      body.classList.remove("swm-sidebar-open");
      return;
    }

    // Desktop: restaura colapsado do localStorage
    const saved = localStorage.getItem(KEY);
    if (saved === "1") body.classList.add("swm-sidebar-collapsed");
    else body.classList.remove("swm-sidebar-collapsed");
  }

  function toggleSidebar() {
    if (isMobile()) {
      body.classList.toggle("swm-sidebar-open");
      return;
    }

    body.classList.toggle("swm-sidebar-collapsed");
    localStorage.setItem(KEY, body.classList.contains("swm-sidebar-collapsed") ? "1" : "0");
  }

  function closeMobile() {
    body.classList.remove("swm-sidebar-open");
  }

  // botões toggle
  document.querySelectorAll("[data-swm-sidebar-toggle]").forEach(btn => {
    btn.addEventListener("click", toggleSidebar);
  });

  // overlay fecha no mobile
  if (overlay) overlay.addEventListener("click", closeMobile);
  document.querySelectorAll("[data-swm-sidebar-close]").forEach(el => {
    el.addEventListener("click", closeMobile);
  });

  // ao redimensionar, re-aplica comportamento
  window.addEventListener("resize", applyInitialState);

  applyInitialState();
})();
