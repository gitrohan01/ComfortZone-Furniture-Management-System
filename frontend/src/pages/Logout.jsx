import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api, { clearAuth } from "../servicess/api";

function Logout() {

    const navigate = useNavigate();

    useEffect(() => {

        const refresh = localStorage.getItem("refresh");
        const finish = () => {
            clearAuth();
            navigate("/login", { replace: true });
        };
        if (refresh) api.post("logout/", { refresh }).finally(finish);
        else finish();

    }, [navigate]);

    return null;
}

export default Logout;
