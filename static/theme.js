(function () {
  const KEY = "docs_theme";
  const root = document.documentElement;

  function setTheme(t) {
    root.setAttribute("data-theme", t);
    localStorage.setItem(KEY, t);
  }

  const saved = localStorage.getItem(KEY);
  if (saved === "light" || saved === "dark") setTheme(saved);

  window.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("themeToggle");
    if (btn) {
      btn.addEventListener("click", () => {
        const cur = root.getAttribute("data-theme") || "dark";
        setTheme(cur === "dark" ? "light" : "dark");
      });
    }

    const FKEY = "docs_tree_open";

    function loadOpenSet() {
      try {
        const raw = localStorage.getItem(FKEY);
        const arr = raw ? JSON.parse(raw) : [];
        return new Set(Array.isArray(arr) ? arr : []);
      } catch {
        return new Set();
      }
    }

    function saveOpenSet(set) {
      localStorage.setItem(FKEY, JSON.stringify([...set]));
    }

    const openSet = loadOpenSet();

    function setFolderState(path, isOpen) {
      const dirNode = document.querySelector(`.node.dir[data-path="${CSS.escape(path)}"]`);
      const children = document.querySelector(`.children[data-children-of="${CSS.escape(path)}"]`);
      if (!dirNode || !children) return;

      if (isOpen) {
        dirNode.classList.add("expanded");
        dirNode.classList.remove("collapsed");
        children.classList.remove("collapsed");
        openSet.add(path);
      } else {
        dirNode.classList.add("collapsed");
        dirNode.classList.remove("expanded");
        children.classList.add("collapsed");
        openSet.delete(path);
      }
    }

    document.querySelectorAll(".node.dir").forEach((d) => {
      const path = d.getAttribute("data-path") || "";
      const shouldOpen = (path === "") || openSet.has(path);
      setFolderState(path, shouldOpen);

      const twisty = d.querySelector(".twisty");
      if (twisty) {
        twisty.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const isOpen = d.classList.contains("expanded");
          setFolderState(path, !isOpen);
          saveOpenSet(openSet);
        });
      }
    });

    const activePath = document.body.getAttribute("data-active-path") || "";
    const browsePath = document.body.getAttribute("data-browse-path") || "";

    if (activePath) {
      const activeNode = document.querySelector(`.node.file[data-path="${CSS.escape(activePath)}"]`);
      if (activeNode) {
        let el = activeNode.parentElement?.closest(".children");
        while (el) {
          const parentPath = el.getAttribute("data-children-of");
          if (parentPath != null) setFolderState(parentPath, true);
          el = el.parentElement ? el.parentElement.closest(".children") : null;
        }
        saveOpenSet(openSet);
        activeNode.scrollIntoView({ block: "center", behavior: "smooth" });
      }
      return;
    }

    if (browsePath) {
      const parts = browsePath.split("/").filter(Boolean);
      let cur = "";
      setFolderState("", true);

      for (const part of parts) {
        cur = cur ? `${cur}/${part}` : part;
        setFolderState(cur, true);
      }
      saveOpenSet(openSet);

      const folderNode = document.querySelector(`.node.dir[data-path="${CSS.escape(browsePath)}"]`);
      if (folderNode) folderNode.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  });
})();