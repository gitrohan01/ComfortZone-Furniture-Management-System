import "../css/Dressing.css";
import CatalogCategory from "../components/CatalogCategory";

const dressings = [
  {
    id: 1,
    name: "Luxury Wooden Dressing Table",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹24,999",
    oldPrice: "₹34,999",
    discount: "29% OFF",
    info: "Premium wooden dressing table with large mirror and storage drawers."
  },

  {
    id: 2,
    name: "Modern Dressing Unit",
    img: "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=700",
    price: "₹18,999",
    oldPrice: "₹26,999",
    discount: "30% OFF",
    info: "Elegant dressing unit with LED mirror and spacious storage."
  },

  {
    id: 3,
    name: "Classic Dressing Table",
    img: "https://images.unsplash.com/photo-1494526585095-c41746248156?w=700",
    price: "₹21,999",
    oldPrice: "₹29,999",
    discount: "27% OFF",
    info: "Classic wooden dressing table with smooth finish and premium quality."
  },

  {
    id: 4,
    name: "Designer Makeup Table",
    img: "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=700",
    price: "₹27,999",
    oldPrice: "₹38,999",
    discount: "28% OFF",
    info: "Luxury dressing table with elegant mirror and modern storage design."
  },

  {
    id: 5,
    name: "Compact Dressing Table",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹16,999",
    oldPrice: "₹22,999",
    discount: "26% OFF",
    info: "Compact dressing table suitable for apartments and small bedrooms."
  },

  {
    id: 6,
    name: "Premium Vanity Table",
    img: "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=700",
    price: "₹31,999",
    oldPrice: "₹42,999",
    discount: "24% OFF",
    info: "Luxury vanity table with large mirror, drawers, and elegant finish."
  }
];

export default function Dressing() {
  return <CatalogCategory
    category="Dressing Table"
    title="Exclusive Dressing Table Collection"
    sectionClass="dressing-section"
    gridClass="dressing-grid"
    cardClass="dressing-card"
    detailsClass="dressing-details"
    fallbackImages={dressings.map(({ img }) => img)}
  />;
}
