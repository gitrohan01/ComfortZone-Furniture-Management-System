import "../css/Sofa.css";
import CatalogCategory from "../components/CatalogCategory";

const sofas = [
  {
    id: 1,
    name: "Luxury Leather Sofa",
    img: "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=700",
    price: "₹52,999",
    oldPrice: "₹69,999",
    discount: "25% OFF",
    info: "Premium genuine leather 3-seater sofa with elegant modern design."
  },

  {
    id: 2,
    name: "Modern Fabric Sofa",
    img: "https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?w=700",
    price: "₹39,999",
    oldPrice: "₹55,999",
    discount: "30% OFF",
    info: "Soft fabric sofa with solid wooden frame and premium comfort."
  },

  {
    id: 3,
    name: "L-Shaped Corner Sofa",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹74,999",
    oldPrice: "₹94,999",
    discount: "21% OFF",
    info: "Luxury L-shaped sofa suitable for spacious modern living rooms."
  },

  {
    id: 4,
    name: "Wooden Designer Sofa",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=700",
    price: "₹45,999",
    oldPrice: "₹61,999",
    discount: "26% OFF",
    info: "Elegant wooden sofa with premium cushions and polished finish."
  },

  {
    id: 5,
    name: "Velvet Luxury Sofa",
    img: "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=700",
    price: "₹59,999",
    oldPrice: "₹79,999",
    discount: "24% OFF",
    info: "Premium velvet sofa with high-density foam cushions."
  },

  {
    id: 6,
    name: "Minimalist Grey Sofa",
    img: "https://images.unsplash.com/photo-1484101403633-562f891dc89a?w=700",
    price: "₹36,999",
    oldPrice: "₹49,999",
    discount: "28% OFF",
    info: "Simple and stylish grey sofa perfect for modern apartments."
  }
];

export default function Sofa() {
  return <CatalogCategory
    category="Sofa"
    title="Exclusive Sofa Collection"
    sectionClass="sofa-section"
    gridClass="sofa-grid"
    cardClass="sofa-card"
    detailsClass="sofa-details"
    fallbackImages={sofas.map(({ img }) => img)}
  />;
}
