import "../css/Wardrobe.css";
import CatalogCategory from "../components/CatalogCategory";

const wardrobes = [
  {
    id: 1,
    name: "Premium Wooden Wardrobe",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹42,999",
    oldPrice: "₹58,999",
    discount: "27% OFF",
    info: "Spacious 4-door wardrobe with premium teak wood finish and modern design."
  },

  {
    id: 2,
    name: "Sliding Door Wardrobe",
    img: "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=700",
    price: "₹36,999",
    oldPrice: "₹49,999",
    discount: "26% OFF",
    info: "Elegant sliding wardrobe with large mirror and smooth sliding doors."
  },

  {
    id: 3,
    name: "Modern Mirror Wardrobe",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹54,999",
    oldPrice: "₹72,999",
    discount: "24% OFF",
    info: "Luxury wardrobe with full-length mirror and multiple storage compartments."
  },

  {
    id: 4,
    name: "Classic Wooden Closet",
    img: "https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?w=700",
    price: "₹31,999",
    oldPrice: "₹42,999",
    discount: "25% OFF",
    info: "Stylish wooden closet with shelves and hanging space."
  },

  {
    id: 5,
    name: "Luxury 5-Door Wardrobe",
    img: "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=700",
    price: "₹67,999",
    oldPrice: "₹89,999",
    discount: "23% OFF",
    info: "Premium wardrobe with five doors, drawers, and elegant finish."
  },

  {
    id: 6,
    name: "Compact Bedroom Wardrobe",
    img: "https://images.unsplash.com/photo-1484101403633-562f891dc89a?w=700",
    price: "₹27,999",
    oldPrice: "₹37,999",
    discount: "26% OFF",
    info: "Compact wardrobe perfect for small bedrooms with smart storage."
  }
];

export default function Wardrobe() {
  return <CatalogCategory
    category="Wardrobe"
    title="Exclusive Wardrobe Collection"
    sectionClass="wardrobe-section"
    gridClass="wardrobe-grid"
    cardClass="wardrobe-card"
    detailsClass="wardrobe-details"
    fallbackImages={wardrobes.map(({ img }) => img)}
  />;
}
