export function saveSetting(key,value){const s=JSON.parse(localStorage.getItem('vidora_settings')||'{}');s[key]=value;localStorage.setItem('vidora_settings',JSON.stringify(s));}
