import React, { createContext, useContext, useState, ReactNode } from 'react';
import { Reviewer } from '../types/api';
import { api, setAuthToken } from '../services/api';

interface AuthContextType {
  token: string | null;
  reviewer: Reviewer | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState<Reviewer | null>(null);

  const login = async (email: string, password: string) => {
    const data = await api.login(email, password);
    setToken(data.access_token);
    setReviewer(data.reviewer);
  };

  const logout = () => {
    setAuthToken(null);
    setToken(null);
    setReviewer(null);
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        reviewer,
        isAuthenticated: !!token,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
