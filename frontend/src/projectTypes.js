// Mirror of backend app/project_types.py -- keep the two in sync. The
// /api/project-types endpoint serves the same data at runtime if a screen
// ever needs the authoritative copy; for the picker and column-visibility
// rules a static mirror keeps the UI simple and fetch-free.
export const PROJECT_TYPES = [
  { value: "wetworks", label: "Wetworks", laborApplies: true, datesRequired: true, bomPerLine: false },
  { value: "loose_furniture", label: "Loose Furniture", laborApplies: false, datesRequired: false, bomPerLine: true },
  { value: "fixed_furniture", label: "Fixed Furniture", laborApplies: false, datesRequired: false, bomPerLine: true },
];

const BY_VALUE = Object.fromEntries(PROJECT_TYPES.map((t) => [t.value, t]));

export const typeConfig = (value) => BY_VALUE[value] || BY_VALUE.wetworks;
export const typeLabel = (value) => typeConfig(value).label;
export const laborApplies = (value) => typeConfig(value).laborApplies;
export const datesRequired = (value) => typeConfig(value).datesRequired;
// Furniture: BOM component quantities are entered per estimate line, and each
// line with components carries a per-project Factory Work charge.
export const bomPerLine = (value) => typeConfig(value).bomPerLine;

// The support-item purchase_category values the furniture component picker
// filters on (mirror of project_types.FURNITURE_BOM_CATEGORIES).
export const FURNITURE_BOM_CATEGORIES = ["Fabric", "Stone", "Metal", "Accessories"];
