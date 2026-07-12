import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { server } from "../mocks/server";

function AuthProbe() {
  const { isAuthenticated, isLoading, logout } = useAuth();
  const [logoutResult, setLogoutResult] = useState("not-requested");

  return (
    <>
      <div>
        {isLoading
          ? "loading"
          : isAuthenticated
            ? "authenticated"
            : "signed-out"}
      </div>
      <div>{logoutResult}</div>
      <button
        type="button"
        onClick={async () => {
          const result = await logout();
          setLogoutResult(
            result.success ? "logout-succeeded" : "logout-failed",
          );
        }}
      >
        Log out
      </button>
    </>
  );
}

describe("AuthContext logout", () => {
  it("keeps the user authenticated when durable revocation fails", async () => {
    server.use(
      http.post("/api/auth/logout", () =>
        HttpResponse.json(
          { success: false, error: "Unable to revoke active sessions" },
          { status: 500 },
        ),
      ),
    );
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await screen.findByText("authenticated");
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await screen.findByText("logout-failed");
    expect(screen.getByText("authenticated")).toBeTruthy();
  });

  it("clears the user only after durable revocation succeeds", async () => {
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await screen.findByText("authenticated");
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => {
      expect(screen.getByText("logout-succeeded")).toBeTruthy();
      expect(screen.getByText("signed-out")).toBeTruthy();
    });
  });

  it("clears local auth when the server session is already invalid", async () => {
    server.use(
      http.post("/api/auth/logout", () =>
        HttpResponse.json(
          { detail: "Session expired or invalid" },
          { status: 401 },
        ),
      ),
    );
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await screen.findByText("authenticated");
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => {
      expect(screen.getByText("logout-succeeded")).toBeTruthy();
      expect(screen.getByText("signed-out")).toBeTruthy();
    });
  });
});
