import "../css/Teapoi.css";
import CatalogCategory from "../components/CatalogCategory";

const teapois = [
  {
    id: 1,
    name: "Modern Wooden Teapoi",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹8,999",
    oldPrice: "₹11,999",
    discount: "25% OFF",
    info: "Premium solid wood teapoi with elegant finish for modern living rooms."
  },

  {
    id: 2,
    name: "Glass Top Coffee Table",
    img: "https://images.unsplash.com/photo-1494526585095-c41746248156?w=700",
    price: "₹10,499",
    oldPrice: "₹13,999",
    discount: "25% OFF",
    info: "Stylish glass-top coffee table with sturdy wooden legs."
  },

  {
    id: 3,
    name: "Designer Center Table",
    img: "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=700",
    price: "₹12,999",
    oldPrice: "₹17,999",
    discount: "28% OFF",
    info: "Luxury designer center table with premium craftsmanship."
  },

  {
    id: 4,
    name: "Round Wooden Coffee Table",
    img: "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=700",
    price: "₹9,499",
    oldPrice: "₹12,999",
    discount: "27% OFF",
    info: "Round wooden coffee table perfect for compact spaces."
  },

  {
    id: 5,
    name: "Premium Marble Teapoi",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹15,999",
    oldPrice: "₹20,999",
    discount: "24% OFF",
    info: "Elegant marble top teapoi with premium metal frame."
  },

  {
    id: 6,
    name: "Minimalist Coffee Table",
    img: "https://images.unsplash.com/photo-1494526585095-c41746248156?w=700",
    price: "₹7,999",
    oldPrice: "₹10,999",
    discount: "27% OFF",
    info: "Simple and modern coffee table suitable for every home."
  }
];

export default function Teapoi() {
  return <CatalogCategory
    category="Teapoi"
    title="Exclusive Teapoi Collection"
    sectionClass="teapoi-section"
    gridClass="teapoi-grid"
    cardClass="teapoi-card"
    detailsClass="teapoi-details"
    fallbackImages={teapois.map(({ img }) => img)}
  />;
}
