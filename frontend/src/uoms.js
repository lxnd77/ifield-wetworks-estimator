// Mirror of backend app/uoms.py -- the Odoo units of measure a product or
// support item may carry (exported as the product import's product_uom).
export const UOMS = [
  "Units", "Bags", "Boards", "Boxes", "Drum", "Nos", "Rolls", "Dozens",
  "g", "oz", "lb", "kg", "t",
  "Hours", "Days",
  "mm", "cm", "in", "ft", "yd", "m", "km", "mi",
  "ft²", "m²",
  "in³", "fl oz (US)", "qt (US)", "L", "gal (US)", "ft³", "m³",
  "Cubic Meter", "Rm", "Sqm",
];

export const DEFAULT_UOM = "Units";
