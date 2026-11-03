import "../css/Chair.css";
import CatalogCategory from "../components/CatalogCategory";

const chairs = [
  {
    id: 1,
    name: "Executive Office Chair",
    img: "https://images.unsplash.com/photo-1505843513577-22bb7d21e455?w=700",
    price: "₹18,999",
    oldPrice: "₹25,999",
    discount: "27% OFF",
    info: "Premium leather executive chair with adjustable height and lumbar support."
  },

  {
    id: 2,
    name: "Ergonomic Mesh Chair",
    img: "https://images.unsplash.com/photo-1580480055273-228ff5388ef8?w=700",
    price: "₹14,999",
    oldPrice: "₹20,999",
    discount: "29% OFF",
    info: "Breathable mesh office chair designed for long working hours."
  },

  {
    id: 3,
    name: "High Back Office Chair",
    img: "https://images.unsplash.com/photo-1519947486511-46149fa0a254?w=700",
    price: "₹16,499",
    oldPrice: "₹22,999",
    discount: "28% OFF",
    info: "Comfortable high-back office chair with premium cushioning."
  },

  {
    id: 4,
    name: "Luxury Boss Chair",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹24,999",
    oldPrice: "₹33,999",
    discount: "26% OFF",
    info: "Luxury office chair with wooden armrests and leather finish."
  },

  {
    id: 5,
    name: "Computer Study Chair",
    img: "https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=700",
    price: "₹11,999",
    oldPrice: "₹16,999",
    discount: "30% OFF",
    info: "Modern study chair with wheels and adjustable seating."
  },

  {
    id: 6,
    name: "Premium Gaming Chair",
    img: "https://images.unsplash.com/photo-1593642532400-2682810df593?w=700",
    price: "₹21,999",
    oldPrice: "₹29,999",
    discount: "27% OFF",
    info: "Gaming-style office chair with neck and lumbar support."
  }
];

export default function Chair() {
  return <CatalogCategory
    category="Chair"
    title="Exclusive Office Chair Collection"
    sectionClass="chair-section"
    gridClass="chair-grid"
    cardClass="chair-card"
    detailsClass="chair-details"
    fallbackImages={chairs.map(({ img }) => img)}
  />;
}
