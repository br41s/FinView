import type { WorldAsset, WorldEvent } from "../model/types";
import s from "../world.module.css";

interface Props { asset: WorldAsset | null; event: WorldEvent }
type Palette = { sky: string; ground: string; wall: string; roof: string; accent: string; glass: string };

const PALETTES: Record<string, Palette> = {
  retail: { sky: "#d9f2ea", ground: "#a9cd83", wall: "#f4e5d1", roof: "#df806b", accent: "#d45d59", glass: "#87c4d1" },
  consumer: { sky: "#e8efd2", ground: "#a5c77c", wall: "#f1dfc5", roof: "#cc8a58", accent: "#e2a83a", glass: "#9fcad0" },
  tech: { sky: "#cce9f5", ground: "#82b7a4", wall: "#dce9ef", roof: "#536e9c", accent: "#28a8c2", glass: "#7ec4de" },
  semis: { sky: "#d6e8f2", ground: "#9fc6a2", wall: "#e8edf0", roof: "#7d91a4", accent: "#36a8b4", glass: "#89c7d2" },
  energy: { sky: "#f0e7d1", ground: "#a5bd83", wall: "#d8d8cf", roof: "#727b7d", accent: "#e3a33b", glass: "#9bbdc1" },
  mining: { sky: "#d9e2e8", ground: "#9a997d", wall: "#a9a99f", roof: "#626a6d", accent: "#e0a13b", glass: "#9ab1b4" },
  banking: { sky: "#d6e8f7", ground: "#9fc58c", wall: "#e9e1d1", roof: "#536f99", accent: "#d5ac53", glass: "#99c2d5" },
  health: { sky: "#d8f0ea", ground: "#a8c98c", wall: "#edf2ed", roof: "#6b9d9b", accent: "#26a88a", glass: "#8ccdd0" },
  telecom: { sky: "#d7eaf6", ground: "#9ec58b", wall: "#dce5eb", roof: "#687c9b", accent: "#4c9bd0", glass: "#8cc4d9" },
  utilities: { sky: "#d8eff5", ground: "#9fc887", wall: "#e6e9e2", roof: "#788f87", accent: "#4da7a0", glass: "#9bd4d2" },
  realestate: { sky: "#dce9f2", ground: "#a7c88d", wall: "#e8e2d8", roof: "#7c8995", accent: "#d58d72", glass: "#8cb6cb" },
  fund: { sky: "#e3e9f4", ground: "#a8c88b", wall: "#e8e6dc", roof: "#657a9d", accent: "#a68bd3", glass: "#a6c4df" },
  cash: { sky: "#e8eadc", ground: "#b3c58f", wall: "#ddd4bd", roof: "#8e826b", accent: "#d6ad40", glass: "#b1c5bb" },
  crypto: { sky: "#d9def4", ground: "#8f9ec0", wall: "#424a68", roof: "#252c49", accent: "#a68cf0", glass: "#71d6dd" },
};
const FALLBACK = PALETTES.consumer;

function SiteArchitecture({ archetype, p }: { archetype: string; p: Palette }) {
  switch (archetype) {
    case "retail":
    case "consumer":
      return <g>
        <path d="M208 210V130l66-37 69 37v80Z" fill={p.wall} stroke="#52616a" strokeWidth="3"/>
        <path d="m208 130 66-38 69 38-69 36Z" fill={p.roof}/>
        <path d="M225 152h101v58H225Z" fill={p.glass} stroke="#536c76" strokeWidth="3"/>
        <path d="M225 166h101M275 152v58" stroke="#e9f4e8" strokeWidth="4"/>
        <path d="M214 178h90v14h-90Z" fill={p.accent}/>
        <path d="M304 178h23v14h-23Z" fill="#e8b85d"/>
        <path d="M232 122h83l18 11h-83Z" fill={p.accent}/>
        <path d="M244 143v-18m38 6v-18m36 38v-18" stroke="#fff4df" strokeWidth="4"/>
        <rect x="236" y="195" width="17" height="15" fill="#805f4d"/>
        <rect x="285" y="194" width="20" height="16" fill="#805f4d"/>
        <path d="M342 178v-52l35-20 34 20v84h-69Z" fill={p.wall} stroke="#64717a" strokeWidth="3"/>
        <path d="m342 126 35-20 34 20-34 19Z" fill={p.roof}/>
        <path d="M354 145h48v27h-48Z" fill={p.glass}/>
        <path d="M354 183h48v18h-48Z" fill={p.accent}/>
        <rect x="430" y="188" width="58" height="27" rx="5" fill="#e6e8e1" stroke="#63727a" strokeWidth="3"/>
        <rect x="439" y="193" width="27" height="13" rx="2" fill={p.glass}/>
        <circle cx="443" cy="218" r="6" fill="#46505b"/><circle cx="478" cy="218" r="6" fill="#46505b"/>
      </g>;
    case "tech":
    case "semis":
      return <g>
        <path d="M200 207V102l55-31 57 31v105Z" fill={p.wall} stroke="#61747d" strokeWidth="3"/>
        <path d="m200 102 55-31 57 31-57 31Z" fill={p.roof}/>
        <path d="M214 112h83v82h-83Z" fill={p.glass} stroke="#e7f7f7" strokeWidth="3"/>
        {[0,1,2].map((i) => <path key={i} d={"M214 "+(132+i*22)+"h83"} stroke="#e8f7f6" strokeWidth="3"/>)}
        {[0,1,2].map((i) => <path key={i} d={"M"+(242+i*27)+" 112v82"} stroke="#e8f7f6" strokeWidth="3"/>)}
        <path d="M324 207v-64l60-34 61 34v64Z" fill={p.wall} stroke="#60717e" strokeWidth="3"/>
        <path d="m324 143 60-34 61 34-61 34Z" fill={p.roof}/>
        <path d="M339 155h89v40h-89Z" fill="#71899a"/>
        {Array.from({length:6},(_,i)=><rect key={i} x={347+i*13} y="161" width="6" height="27" rx="2" fill={p.glass}/>)}
        <path d="M236 69V48m-8 6h16m87 52V76m-6 8h12" stroke="#52697b" strokeWidth="4" strokeLinecap="round"/>
        <circle cx="255" cy="70" r="5" fill={p.accent}/>
        <path d="M178 209h320" stroke="#667f91" strokeWidth="7" strokeLinecap="round"/>
      </g>;
    case "energy":
    case "utilities":
      return <g>
        <path d="M194 210V170h294v40Z" fill={p.wall} stroke="#6b7574" strokeWidth="3"/>
        <path d="M220 170V119c0-17 23-27 44-27s44 10 44 27v51Z" fill={p.wall} stroke="#6a7472" strokeWidth="3"/>
        <ellipse cx="264" cy="119" rx="44" ry="14" fill="#eef1e8" stroke="#6a7472" strokeWidth="3"/>
        <path d="M224 144h80" stroke={p.accent} strokeWidth="7"/>
        <path d="M330 170V132c0-15 18-24 35-24s35 9 35 24v38Z" fill="#d7ded7" stroke="#687674" strokeWidth="3"/>
        <ellipse cx="365" cy="132" rx="35" ry="12" fill="#eff2e9" stroke="#687674" strokeWidth="3"/>
        <path d="M422 172V93h18v79" fill="#8d9893" stroke="#5b6868" strokeWidth="3"/>
        <path d="M418 93h26l-4-16h-18Z" fill={p.roof}/>
        <path d="M200 186h286m-242-17v17m65-17v17m64-17v17" stroke="#87928b" strokeWidth="5"/>
        <path d="M270 85v-18h48v18m-48-8h48" stroke={p.accent} strokeWidth="4" fill="none"/>
        <path d="M457 177h31v-35" stroke="#6d7b78" strokeWidth="7" fill="none"/>
        <circle cx="482" cy="139" r="5" fill={p.accent}/>
      </g>;
    case "mining":
      return <g>
        <path d="M160 216 207 142l49-27 47 30 48-47 59 36 55 82Z" fill="#817e70" stroke="#625f57" strokeWidth="3"/>
        <path d="m182 210 43-46 35 7 47-42 46 27 45-26 69 80Z" fill="#a89c82"/>
        <path d="M226 164h63m-63 0-15 23h81l15-23" stroke="#d7bd83" strokeWidth="8" fill="none"/>
        <path d="M291 145 359 99l83 44" stroke="#4d5b63" strokeWidth="8" fill="none"/>
        <path d="M301 140 366 96l80 44" stroke={p.accent} strokeWidth="3" fill="none"/>
        <path d="M340 178h83v36h-83Z" fill={p.wall} stroke="#59636a" strokeWidth="3"/>
        <path d="M352 178v-19h58v19" fill={p.roof}/>
        <path d="M424 152v-39h13v39" fill="#656c6c"/>
        <path d="M429 113h20l-4-10h-12Z" fill={p.accent}/>
        <circle cx="269" cy="197" r="8" fill="#d4a84d"/><circle cx="287" cy="202" r="6" fill="#bd8d48"/>
      </g>;
    case "banking":
    case "fund":
    case "cash":
      return <g>
        <path d="M196 135 335 73l140 62v14H196Z" fill={p.roof} stroke="#596c7e" strokeWidth="3"/>
        <path d="M210 149h250v61H210Z" fill={p.wall} stroke="#687681" strokeWidth="3"/>
        {[0,1,2,3,4].map((i)=><g key={i}><path d={"M"+(232+i*49)+" 151v55"} stroke="#fff3db" strokeWidth="10"/><path d={"M"+(232+i*49)+" 151v55"} stroke="#8d9ba2" strokeWidth="2"/></g>)}
        <path d="M191 210h290v12H191Z" fill="#8d9ca3"/>
        <path d="M250 222h168l-20 12H270Z" fill="#c5b99e"/>
        <path d="M311 181h48v29h-48Z" fill={p.glass}/>
        <circle cx="335" cy="100" r="12" fill={p.accent}/>
        <path d="M335 88v24m-11-12h22" stroke="#fff8df" strokeWidth="3"/>
      </g>;
    case "health":
      return <g>
        <path d="M205 208V121l69-35 69 35v87Z" fill={p.wall} stroke="#61777a" strokeWidth="3"/>
        <path d="m205 121 69-35 69 35-69 35Z" fill={p.roof}/>
        <path d="M221 145h105v47H221Z" fill={p.glass} stroke="#fff" strokeWidth="3"/>
        {[0,1,2,3].map((i)=><path key={i} d={"M"+(245+i*25)+" 145v47"} stroke="#eff7f4" strokeWidth="3"/>)}
        <path d="M355 208v-59l60-31 60 31v59Z" fill="#e9efeb" stroke="#607476" strokeWidth="3"/>
        <path d="m355 149 60-31 60 31-60 31Z" fill="#82b5b8"/>
        <rect x="395" y="153" width="39" height="36" rx="4" fill={p.accent}/>
        <path d="M414 159v24m-12-12h24" stroke="#fff" strokeWidth="7" strokeLinecap="round"/>
        <path d="M260 91v-24h27v24" fill={p.accent}/>
      </g>;
    case "telecom":
      return <g>
        <path d="M224 213 300 70l76 143" stroke="#6b7f8b" strokeWidth="8" fill="none"/>
        <path d="M246 172h108m-87-39h66m-44-40h23" stroke="#687c8b" strokeWidth="5"/>
        <path d="M300 70v-17m-18 9a26 26 0 0 1 36 0m-51-13a45 45 0 0 1 66 0" stroke={p.accent} strokeWidth="5" fill="none" strokeLinecap="round"/>
        <path d="M375 211v-58l53-28 53 28v58Z" fill={p.wall} stroke="#657785" strokeWidth="3"/>
        <path d="m375 153 53-28 53 28-53 28Z" fill={p.roof}/>
        <path d="M390 168h76v28h-76Z" fill={p.glass}/>
      </g>;
    case "realestate":
      return <g>
        <path d="M225 211V82l67-34 69 34v129Z" fill={p.wall} stroke="#687984" strokeWidth="3"/>
        <path d="m225 82 67-34 69 34-69 35Z" fill={p.roof}/>
        <path d="M241 97h100v98H241Z" fill={p.glass}/>
        {[0,1,2,3].map((i)=><path key={i} d={"M241 "+(117+i*22)+"h100"} stroke="#e8f6f5" strokeWidth="4"/>)}
        <path d="M379 211V119l54-28 55 28v92Z" fill="#ddd9d0" stroke="#72818a" strokeWidth="3"/>
        <path d="m379 119 54-28 55 28-55 28Z" fill={p.accent}/>
        <path d="M394 137h83v54h-83Z" fill={p.glass}/>
      </g>;
    case "crypto":
      return <g>
        <path d="M227 211V120l65-38 66 38v91Z" fill="#343e60" stroke="#8182bf" strokeWidth="3"/>
        <path d="m227 120 65-38 66 38-66 36Z" fill="#515a82"/>
        <path d="M248 143h87v51h-87Z" fill="#6ad0d5"/>
        <path d="M271 144v49m21-49v49m21-49v49" stroke="#283653" strokeWidth="4"/>
        <circle cx="419" cy="153" r="58" fill={p.accent} stroke="#e4d8ff" strokeWidth="6"/>
        <circle cx="419" cy="153" r="43" fill="#353b66"/>
        <path d="M419 119v68m-16-49h25a11 11 0 0 1 0 22h-24m0 0h27a11 11 0 0 1 0 22h-27" stroke="#c5f5f0" strokeWidth="9" fill="none" strokeLinecap="round"/>
      </g>;
    default:
      return <g>
        <path d="M215 210V125l62-35 63 35v85Z" fill={p.wall} stroke="#677782" strokeWidth="3"/>
        <path d="m215 125 62-35 63 35-63 34Z" fill={p.roof}/>
        <path d="M232 151h91v42h-91Z" fill={p.glass}/>
        {[0,1,2].map((i)=><path key={i} d={"M"+(252+i*28)+" 151v42"} stroke="#fff" strokeWidth="3"/>)}
      </g>;
  }
}

function EventGlyph({ type, accent }: { type: WorldEvent["eventType"]; accent: string }) {
  if (type === "price_move_down" || type === "earnings_miss") {
    return <g><circle cx="630" cy="72" r="32" fill="#fff" opacity=".92"/><path d="m613 58 17 23 17-12" fill="none" stroke="#d84d49" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round"/></g>;
  }
  if (type === "dividend_paid" || type === "dividend_declared") {
    return <g><circle cx="630" cy="72" r="32" fill="#fff" opacity=".92"/><circle cx="630" cy="72" r="20" fill="#e5b94d"/><path d="M630 57v30m-8-22h13a6 6 0 0 1 0 12h-12" stroke="#fff" strokeWidth="4" fill="none"/></g>;
  }
  if (type === "site_expansion" || type === "position_added") {
    return <g><circle cx="630" cy="72" r="32" fill="#fff" opacity=".92"/><path d="M630 52v40m-20-20h40" stroke={accent} strokeWidth="8" strokeLinecap="round"/></g>;
  }
  if (type === "technical_signal" || type === "options_alert") {
    return <g><circle cx="630" cy="72" r="32" fill="#fff" opacity=".92"/><path d="m610 83 12-17 11 9 17-22" stroke={accent} strokeWidth="6" fill="none" strokeLinecap="round" strokeLinejoin="round"/></g>;
  }
  return <g><circle cx="630" cy="72" r="32" fill="#fff" opacity=".92"/><path d="m630 51 7 14 16 2-12 11 3 16-14-8-14 8 3-16-12-11 16-2Z" fill={accent}/></g>;
}

export function EventIllustration({ asset, event }: Readonly<Props>) {
  const archetype = asset?.archetype ?? "consumer";
  const p = PALETTES[archetype] ?? FALLBACK;
  const id = event.id.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 32) || "event";
  const title = asset?.ticker ?? asset?.name ?? "FinView";
  return <svg className={s.eventArt} viewBox="0 0 760 286" role="img"
    aria-label={"Ilustración de "+title+": "+event.title} preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id={"sky-"+id} x1="0" x2="1" y1="0" y2="1">
        <stop offset="0%" stopColor={p.sky}/><stop offset="100%" stopColor={p.glass}/>
      </linearGradient>
      <linearGradient id={"floor-"+id} x1="0" x2="1" y1="0" y2="1">
        <stop offset="0%" stopColor={p.ground}/><stop offset="100%" stopColor="#729d76"/>
      </linearGradient>
    </defs>
    <rect width="760" height="286" fill={"url(#sky-"+id+")"}/>
    <circle cx="92" cy="52" r="31" fill="#fff" opacity=".28"/><circle cx="152" cy="36" r="19" fill="#fff" opacity=".2"/>
    <path d="M0 204 138 169 305 195 470 159 760 200v86H0Z" fill={"url(#floor-"+id+")"}/>
    <path d="M0 235 194 192 381 232 574 190 760 229" stroke="#d7dfc8" strokeWidth="5" fill="none" opacity=".7"/>
    <path d="M0 261 181 220 360 263 555 218 760 258" stroke="#e5ead7" strokeWidth="3" fill="none" opacity=".55"/>
    <g opacity=".95">
      <path d="M56 223v-29m-14 7 14-23 14 23" stroke="#745b43" strokeWidth="7" fill="none" strokeLinecap="round"/>
      <circle cx="56" cy="181" r="17" fill="#4e966c"/><circle cx="45" cy="185" r="12" fill="#63aa78"/>
      <path d="M695 223v-31m-14 7 14-25 14 25" stroke="#745b43" strokeWidth="7" fill="none" strokeLinecap="round"/>
      <circle cx="695" cy="175" r="18" fill="#4c946a"/><circle cx="706" cy="181" r="12" fill="#6aad79"/>
    </g>
    <path d="M85 235 381 174 677 238 381 286Z" fill="#aeb6b3" opacity=".84"/>
    <path d="m105 235 274-58 270 60" stroke="#eef0e6" strokeWidth="4" strokeDasharray="16 13" fill="none"/>
    <SiteArchitecture archetype={archetype} p={p}/>
    <g>
      <circle cx="169" cy="205" r="7" fill="#e6b99b"/><path d="M169 212v18m0-10-8 9m8-9 8 8" stroke="#3d6681" strokeWidth="6" strokeLinecap="round"/>
      <circle cx="512" cy="215" r="7" fill="#c98f6b"/><path d="M512 222v17m0-9-8 7m8-7 8 7" stroke="#d57a57" strokeWidth="6" strokeLinecap="round"/>
      <circle cx="582" cy="229" r="6" fill="#f0c3a0"/><path d="M582 235v14m0-8-7 6m7-6 7 6" stroke="#466f8c" strokeWidth="5" strokeLinecap="round"/>
    </g>
    <g>
      <rect x="26" y="20" width="170" height="38" rx="19" fill="#142b3d" opacity=".76"/>
      <text x="48" y="45" fontSize="18" fontWeight="800" fill="#fff" letterSpacing="2">{title.slice(0,16).toUpperCase()}</text>
    </g>
    <EventGlyph type={event.eventType} accent={p.accent}/>
    <g opacity=".8"><path d="M536 48h46m-23-23v46" stroke="#fff" strokeWidth="2" opacity=".35"/><circle cx="720" cy="18" r="3" fill="#fff"/><circle cx="694" cy="48" r="2" fill="#fff"/></g>
  </svg>;
}
