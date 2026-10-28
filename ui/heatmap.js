export default function({parentElement, data, setStateValue}) {
  const root = parentElement.querySelector('.heatmap');
  root.replaceChildren();
  const table = document.createElement('table');
  const head = document.createElement('thead');
  const header = document.createElement('tr');
  const boundaryClass = text => text.slice(3, 5) === '00' ? 'hour-boundary' : '';
  const dateHeading = document.createElement('th'); dateHeading.setAttribute('aria-label', '날짜'); dateHeading.scope = 'col'; header.append(dateHeading);
  for (const text of data.headers) {
    const th = document.createElement('th'); th.scope = 'col'; th.title = text;
    th.className = boundaryClass(text);
    const hour = document.createElement('span'); hour.className = 'time-hour'; hour.textContent = text.slice(0, 2);
    if (text.endsWith('⁺¹')) {
      const nextDay = document.createElement('sup'); nextDay.textContent = '+1'; hour.append(nextDay);
    }
    th.append(hour);
    if (data.headers.length === 48 || text.slice(3, 5) !== '00') {
      const minute = document.createElement('span'); minute.className = 'time-minute'; minute.textContent = text.slice(3, 5); th.append(minute);
    }
    header.append(th);
  }
  const maxHeading = document.createElement('th'); maxHeading.textContent = '최대'; maxHeading.scope = 'col'; header.append(maxHeading);
  head.append(header); table.append(head);
  const body = document.createElement('tbody');
  let selected = data.selected;
  const palette = data.palette;
  const colorIndex = value => value === 0 ? 0 : data.maximum <= 1 ? palette.length - 1 : Math.min(palette.length - 1, 1 + Math.floor((value - 1) * (palette.length - 2) / (data.maximum - 1)));
  for (let row = 0; row < data.rows.length; row++) {
    const tr = document.createElement('tr');
    const label = document.createElement('th'); label.scope = 'row'; label.title = data.rows[row];
    const weekday = ['일', '월', '화', '수', '목', '금', '토'][new Date(`${data.rows[row]}T00:00:00Z`).getUTCDay()];
    label.textContent = `${data.rows[row].slice(5).replace('-', '/')} (${weekday})`; tr.append(label);
    for (let col = 0; col < data.headers.length; col++) {
      const index = row * data.headers.length + col;
      const cell = document.createElement('td');
      cell.className = boundaryClass(data.headers[col]);
      const button = document.createElement('button');
      const value = data.values[row][col]; const ci = colorIndex(value);
      button.textContent = value;
      button.style.background = palette[ci]; button.style.color = data.textPalette[ci];
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
