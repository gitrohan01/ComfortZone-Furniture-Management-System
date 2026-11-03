import "../css/Dining.css";
import CatalogCategory from "../components/CatalogCategory";

const diningTables = [
  {
    id: 1,
    name: "6 Seater Wooden Dining Set",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹48,999",
    oldPrice: "₹64,999",
    discount: "25% OFF",
    info: "Premium solid wood 6-seater dining table with comfortable cushioned chairs."
  },

  {
    id: 2,
    name: "Modern 4 Seater Dining Table",
    img: "https://images.unsplash.com/photo-1494526585095-c41746248156?w=700",
    price: "₹32,999",
    oldPrice: "₹44,999",
    discount: "26% OFF",
    info: "Compact dining set perfect for modern apartments and small families."
  },

  {
    id: 3,
    name: "Luxury Marble Dining Set",
    img: "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=700",
    price: "₹72,999",
    oldPrice: "₹95,999",
    discount: "24% OFF",
    info: "Elegant marble-top dining table with premium upholstered chairs."
  },

  {
    id: 4,
    name: "Classic Wooden Dining Table",
    img: "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=700",
    price: "₹39,999",
    oldPrice: "₹53,999",
    discount: "25% OFF",
    info: "Traditional wooden dining table with stylish handcrafted finish."
  },

  {
    id: 5,
    name: "8 Seater Premium Dining Set",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹84,999",
    oldPrice: "₹1,09,999",
    discount: "23% OFF",
    info: "Luxury 8-seater dining set ideal for large families and gatherings."
  },

  {
    id: 6,
    name: "Glass Top Dining Table",
    img: "https://images.unsplash.com/photo-1494526585095-c41746248156?w=700",
    price: "₹36,999",
    oldPrice: "₹49,999",
    discount: "25% OFF",
    info: "Modern glass-top dining table with elegant steel frame."
  }
];

export default function Dining() {
  return <CatalogCategory
    category="Dining"
    title="Exclusive Dining Table Collection"
    sectionClass="dining-section"
    gridClass="dining-grid"
    cardClass="dining-card"
    detailsClass="dining-details"
    fallbackImages={diningTables.map(({ img }) => img)}
  />;
}
