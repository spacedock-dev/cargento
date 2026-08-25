function renderNext(){
  const app = document.getElementById("app");
  if(!app) return;
  app.innerHTML = '<div class="next-breadcrumb">Cargento | overview</div>';
}

renderNext();
