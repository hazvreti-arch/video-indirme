// Library helpers are intentionally kept separate for future UI expansion.
export async function searchLibrary(query){return fetch('/api/history').then(r=>r.json()).then(rows=>rows.filter(x=>(x.title||'').toLowerCase().includes(query.toLowerCase())))}
