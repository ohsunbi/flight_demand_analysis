export default function({parentElement, data, setStateValue}) {
  const root = parentElement.querySelector('.heatmap');
  root.replaceChildren();
  const table = document.createElement('table');
  const head = document.createElement('thead');
  const header = document.createElement('tr');
  for (const text of ['운영일', ...data.headers, '최대']) {
    const th = document.createElement('th'); th.textContent = text; header.append(th);
  }
  head.append(header); table.append(head);
  const body = document.createElement('tbody');
  let selected = data.selected;
  const palette = data.palette;
  const colorIndex = value => value === 0 ? 0 : data.maximum <= 1 ? palette.length - 1 : Math.min(palette.length - 1, 1 + Math.floor((value - 1) * (palette.length - 2) / (data.maximum - 1)));
  for (let row = 0; row < data.rows.length; row++) {
    const tr = document.createElement('tr');
    const label = document.createElement('th'); label.textContent = data.rows[row]; tr.append(label);
    for (let col = 0; col < data.headers.length; col++) {
      const index = row * data.headers.length + col;
      const cell = document.createElement('td');
      const button = document.createElement('button');
      const value = data.values[row][col]; const ci = colorIndex(value);
      button.textContent = value;
      button.style.background = palette[ci]; button.style.color = ci >= 4 ? '#fff' : '#123e4c';
      button.dataset.cell = index; button.setAttribute('aria-label', `${data.rows[row]} ${data.headers[col]} 최대 ${value}개 조`);
      button.setAttribute('aria-pressed', String(index === selected));
      button.title = `${data.rows[row]} ${data.headers[col]} · ${value}개 조`;
      button.onclick = () => {
        selected = index;
        root.querySelectorAll('button[aria-pressed="true"]').forEach(b => b.setAttribute('aria-pressed', 'false'));
        button.setAttribute('aria-pressed', 'true');
        setStateValue('selection', index);
      };
      cell.append(button); tr.append(cell);
    }
    const max = document.createElement('td'); max.className = 'daily'; max.textContent = data.daily[row]; tr.append(max);
    body.append(tr);
  }
  table.append(body); root.append(table);
}
