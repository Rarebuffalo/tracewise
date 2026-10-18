import { render } from "@testing-library/react";
import { Button } from "./Button";

test("Button renders label", () => {





  const { container } = render(<Button label="Purchase" />);
  expect(container).toMatchSnapshot();
});
