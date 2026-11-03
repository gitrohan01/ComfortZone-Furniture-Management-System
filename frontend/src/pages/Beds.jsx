import "../css/Beds.css";
import CatalogCategory from "../components/CatalogCategory";

const beds = [
  {
    id: 1,
    name: "Luxury Wooden King Bed",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=600",
    price: "₹45,999",
    oldPrice: "₹65,999",
    discount: "30% OFF",
    info: "Solid teak wood king size bed with premium finish and strong durability."
  },

  {
    id: 2,
    name: "Modern Queen Size Bed",
    img: "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=600",
    price: "₹32,999",
    oldPrice: "₹48,999",
    discount: "35% OFF",
    info: "Elegant queen bed with storage space and modern bedroom design."
  },

  {
    id: 3,
    name: "Premium Storage Bed",
    img: "https://images.unsplash.com/photo-1618220179428-22790b461013?w=600",
    price: "₹55,999",
    oldPrice: "₹79,999",
    discount: "25% OFF",
    info: "Hydraulic storage bed with high-quality wood and smooth finishing."
  },

  {
    id: 4,
    name: "Classic Wooden Double Bed",
    img: "https://images.unsplash.com/photo-1595526114035-0d45ed16cfbf?w=600",
    price: "₹28,999",
    oldPrice: "₹39,999",
    discount: "28% OFF",
    info: "Classic design double bed suitable for stylish home interiors."
  }
];


export default function Beds() {
  return <CatalogCategory
    category="Bed"
    title="Exclusive Bed Collection"
    sectionClass="beds-section"
    gridClass="beds-grid"
    cardClass="bed-card"
    detailsClass="bed-details"
    fallbackImages={beds.map(({ img }) => img)}
  />;
}
